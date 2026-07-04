"""
Stock Intel API — FastAPI backend
Manual CSV data uploads. No scraping. No external APIs.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn, math, threading, os, time, sys
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

from services.data_loader import DataLoader
from services.scoring import ScoringEngine
from services.portfolio import PortfolioManager
from services.analytics import AnalyticsEngine
from services.csv_data_manager import get_manager, generate_price_template, generate_fundamentals_template
from services.technical import compute_technical
from services.valuation import compute_valuation
from services.risk import compute_portfolio_risk
from services.macro import compute_global_intelligence
from services.country import compute_country_intelligence
from services.sector import compute_sector_industry_intelligence
from services.capital_flow import compute_capital_flow
from services.recommendation import synthesize_recommendation, compute_adaptive_weights
from services.continuous_learning import (
    log_recommendation, record_outcome, get_recommendation_history, get_accuracy_stats,
    get_component_effectiveness,
)

# ── Keep-alive: robust external ping via UptimeRobot or self-ping ──────────
def _app_base_path() -> Path:
    """
    Resolves the correct base directory whether running as normal
    Python (dev mode) or as a PyInstaller-frozen single-file
    executable (sys._MEIPASS points at the temp extraction dir).
    Needed so VERSION and the bundled frontend/static files are found
    correctly in both cases without maintaining two code paths.
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent


def _read_version() -> str:
    """Single source of truth: the VERSION file at repo root, bumped
    automatically by the release workflow. Falls back to 'dev' if
    running from source without that file (e.g. a fresh git clone
    before any release has happened)."""
    try:
        version_file = _app_base_path() / "VERSION"
        if version_file.exists():
            return version_file.read_text().strip()
    except Exception:
        pass
    return "dev"


APP_VERSION = _read_version()


def _start_keep_alive():
    """
    Two-layer keep-alive for Render free tier:
    1. Self-ping every 14 min (keeps process warm between external pings)
    2. Designed to work WITH UptimeRobot free plan pinging /api/ping every 5 min

    Set RENDER_EXTERNAL_URL env var in Render dashboard to enable self-ping.
    Also add UptimeRobot monitor: https://your-app.onrender.com/api/ping

    Only does anything when RENDER_EXTERNAL_URL is actually set — a local
    desktop .exe user has no business seeing "configure this in Render"
    messages for a hosting platform they're not using. Silent no-op
    otherwise, not a printed instruction aimed at the wrong audience.
    """
    self_url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not self_url:
        return  # not running on Render — nothing to do, nothing to print

    def _loop():
        time.sleep(90)  # wait for startup
        ping_url = f"{self_url}/api/ping"
        print(f"[keep-alive] Self-ping every 14 min -> {ping_url}")
        while True:
            try:
                import requests as _req
                r = _req.get(ping_url, timeout=15)
                print(f"[keep-alive] OK {r.status_code} at {datetime.now().strftime('%H:%M:%S')}")
            except Exception as e:
                print(f"[keep-alive] ping failed: {e}")
            time.sleep(14 * 60)
    threading.Thread(target=_loop, daemon=True).start()


def _run_daily_price_snapshot():
    """
    Runs the real-price-history-accumulation job (see
    CSVDataManager.snapshot_daily_prices for the ACID guarantees).
    Deliberately called in a background thread from startup, never
    on the request path — a scraper call across 55 tickers can take
    a few seconds, and the app must be responsive immediately, not
    after that finishes. Failure here is non-fatal: if the scraper
    is unreachable (e.g. no internet in this environment), the app
    keeps running normally on whatever history already exists.
    """
    try:
        from services.nse_scraper import get_all_prices
        live_prices = get_all_prices()  # internally cached ~4h — cheap to call often
        if not live_prices:
            print("[snapshot] scraper returned no prices — skipping (app continues normally)")
            return
        result = get_manager().snapshot_daily_prices(live_prices)
        print(f"[snapshot] {result['date']}: added {result['total_added']} tickers "
              f"({len(result['skipped_duplicate'])} already had today, "
              f"{len(result['skipped_no_price'])} had no valid price)")
    except Exception as e:
        print(f"[snapshot] failed (non-fatal, app continues normally): {e}")


def _start_daily_snapshot_thread():
    """Runs once immediately at startup, then once every 24h — not
    request-triggered, so it never adds latency to anything a user
    is waiting on."""
    def _loop():
        while True:
            _run_daily_price_snapshot()
            time.sleep(24 * 3600)
    threading.Thread(target=_loop, daemon=True).start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load local data (fast — no network calls)
    print("[startup] Loading local CSV data...")
    mgr = get_manager()
    meta = mgr.get_upload_meta()
    price_count = meta.get("prices_ticker_count", 0)
    fund_count  = meta.get("fundamentals_ticker_count", 0)
    print(f"[startup] Loaded: {price_count} prices, {fund_count} fundamentals from CSV")
    _start_keep_alive()
    _start_daily_snapshot_thread()
    print("[startup] Ready.")
    yield

app = FastAPI(title="Stock Intel API", version=APP_VERSION, lifespan=lifespan)

# CORS: wildcard origin + allow_credentials=True is invalid per the CORS spec
# (browsers reject it for credentialed requests) and an unnecessarily open
# security posture regardless. Configure via ALLOWED_ORIGINS env var
# (comma-separated) for production; defaults to common local dev ports.
_allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "").strip()
if _allowed_origins_env:
    _allowed_origins = [o.strip() for o in _allowed_origins_env.split(",") if o.strip()]
else:
    _allowed_origins = [
        "http://localhost:5173", "http://127.0.0.1:5173",  # vite dev
        "http://localhost:3000", "http://127.0.0.1:3000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

loader    = DataLoader()
scorer    = ScoringEngine()
portfolio = PortfolioManager()
analytics = AnalyticsEngine()

# Full NSE ticker list
NSE_TICKERS = [
    # ── Banking (11) ──────────────────────────────────────────────────────
    {"ticker": "EQTY", "name": "Equity Group Holdings",       "sector": "Banking"},
    {"ticker": "KCB",  "name": "KCB Group",                   "sector": "Banking"},
    {"ticker": "COOP", "name": "Co-operative Bank of Kenya",  "sector": "Banking"},
    {"ticker": "ABSA", "name": "ABSA Bank Kenya",             "sector": "Banking"},
    {"ticker": "NCBA", "name": "NCBA Group",                  "sector": "Banking"},
    {"ticker": "DTK",  "name": "Diamond Trust Bank Kenya",    "sector": "Banking"},
    {"ticker": "SCBK", "name": "Standard Chartered Kenya",    "sector": "Banking"},
    {"ticker": "IMH",  "name": "I & M Holdings",              "sector": "Banking"},
    {"ticker": "HFCK", "name": "HF Group",                    "sector": "Banking"},
    {"ticker": "SBIC", "name": "Stanbic Holdings",            "sector": "Banking"},
    {"ticker": "BKG",  "name": "BK Group",                    "sector": "Banking"},
    # ── Telecommunication (1) ─────────────────────────────────────────────
    {"ticker": "SCOM", "name": "Safaricom",                   "sector": "Telecommunication"},
    # ── Manufacturing & Allied (8) ────────────────────────────────────────
    {"ticker": "EABL", "name": "East African Breweries",      "sector": "Manufacturing & Allied"},
    {"ticker": "BAT",  "name": "British American Tobacco Kenya","sector": "Manufacturing & Allied"},
    {"ticker": "UNGA", "name": "Unga Group",                  "sector": "Manufacturing & Allied"},
    {"ticker": "AMAC", "name": "Africa Mega Agricorp",        "sector": "Manufacturing & Allied"},
    {"ticker": "CARB", "name": "Carbacid Investments",        "sector": "Manufacturing & Allied"},
    {"ticker": "BOC",  "name": "BOC Kenya",                   "sector": "Manufacturing & Allied"},
    {"ticker": "FTGH", "name": "Flame Tree Group Holdings",   "sector": "Manufacturing & Allied"},
    {"ticker": "SKL",  "name": "Shri Krishana Overseas",      "sector": "Manufacturing & Allied"},
    # ── Insurance (6) ─────────────────────────────────────────────────────
    {"ticker": "JUB",  "name": "Jubilee Holdings",            "sector": "Insurance"},
    {"ticker": "BRIT", "name": "Britam Holdings",             "sector": "Insurance"},
    {"ticker": "CIC",  "name": "CIC Insurance Group",         "sector": "Insurance"},
    {"ticker": "KNRE", "name": "Kenya Re Insurance",          "sector": "Insurance"},
    {"ticker": "LBTY", "name": "Liberty Kenya Holdings",      "sector": "Insurance"},
    {"ticker": "SLAM", "name": "Sanlam Kenya",                "sector": "Insurance"},
    # ── Energy & Petroleum (6) ────────────────────────────────────────────
    {"ticker": "KEGN", "name": "KenGen",                      "sector": "Energy & Petroleum"},
    {"ticker": "KPLC", "name": "Kenya Power & Lighting",      "sector": "Energy & Petroleum"},
    {"ticker": "TOTL", "name": "TotalEnergies Marketing Kenya","sector": "Energy & Petroleum"},
    {"ticker": "UMME", "name": "Umeme",                       "sector": "Energy & Petroleum"},
    {"ticker": "KENOL","name": "Rubis Energy Kenya",          "sector": "Energy & Petroleum"},
    {"ticker": "KPC",  "name": "Kenya Pipeline Company",      "sector": "Energy & Petroleum"},
    # ── Construction & Allied (3) ─────────────────────────────────────────
    {"ticker": "BAMB", "name": "Bamburi Cement",              "sector": "Construction & Allied"},
    {"ticker": "PORT", "name": "East African Portland Cement","sector": "Construction & Allied"},
    {"ticker": "CRWN", "name": "Crown Paints Kenya",          "sector": "Construction & Allied"},
    # ── Agricultural (5) ──────────────────────────────────────────────────
    {"ticker": "SASN", "name": "Sasini",                      "sector": "Agricultural"},
    {"ticker": "KAPC", "name": "Kapchorua Tea Kenya",         "sector": "Agricultural"},
    {"ticker": "LIMT", "name": "Limuru Tea",                  "sector": "Agricultural"},
    {"ticker": "KUKZ", "name": "Kakuzi",                      "sector": "Agricultural"},
    {"ticker": "EGAD", "name": "Eaagads",                     "sector": "Agricultural"},
    # ── Commercial & Services (10) ────────────────────────────────────────
    {"ticker": "TPSE", "name": "TPS Eastern Africa (Serena)", "sector": "Commercial & Services"},
    {"ticker": "NMG",  "name": "Nation Media Group",          "sector": "Commercial & Services"},
    {"ticker": "SGL",  "name": "Standard Group",              "sector": "Commercial & Services"},
    {"ticker": "EVRD", "name": "Eveready East Africa",        "sector": "Commercial & Services"},
    {"ticker": "XPRS", "name": "Express Kenya",               "sector": "Commercial & Services"},
    {"ticker": "SMER", "name": "Sameer Africa",               "sector": "Commercial & Services"},
    {"ticker": "LKL",  "name": "Longhorn Publishers",         "sector": "Commercial & Services"},
    {"ticker": "NBV",  "name": "Nairobi Business Ventures",   "sector": "Commercial & Services"},
    {"ticker": "UCHM", "name": "Uchumi Supermarket",          "sector": "Commercial & Services"},
    {"ticker": "KQ",   "name": "Kenya Airways",               "sector": "Commercial & Services"},
    # ── Automobiles & Accessories (1) ─────────────────────────────────────
    {"ticker": "CGEN", "name": "Car & General Kenya",         "sector": "Automobiles & Accessories"},
    # ── Investment (3) ────────────────────────────────────────────────────
    {"ticker": "CTUM", "name": "Centum Investment",           "sector": "Investment"},
    {"ticker": "HAFR", "name": "Home Afrika",                 "sector": "Investment"},
    {"ticker": "OCH",  "name": "Olympia Capital Holdings",    "sector": "Investment"},
    # ── Investment Services (1) ───────────────────────────────────────────
    {"ticker": "NSE",  "name": "Nairobi Securities Exchange", "sector": "Investment Services"},
]

_score_cache: dict = {}


def _clean(val):
    if val is None:
        return None
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return val


def _clean_dict(d: dict) -> dict:
    return {k: _clean(v) for k, v in d.items()}


# ── Models ─────────────────────────────────────────────────────────────────

class TradeRequest(BaseModel):
    ticker: str
    trade_type: str
    quantity: float
    price: float
    date: str

class MissingDataRequest(BaseModel):
    ticker: str
    field_name: str
    value: str
    source: str

class WatchlistRequest(BaseModel):
    ticker: str

class AlertRequest(BaseModel):
    ticker: str
    alert_type: str
    threshold: float

class ManualPriceRequest(BaseModel):
    ticker: str
    price: float
    date: Optional[str] = None

class ManualFundamentalRequest(BaseModel):
    ticker: str
    field: str
    value: float


# ── Health & keep-alive ────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "Stock Intel API v5", "status": "running", "mode": "manual_csv"}

@app.get("/api/version")
def get_version():
    """
    Current running version — bumped automatically by the GitHub
    Actions release workflow (VERSION file at repo root). Client
    systems should call this first, then /api/version/check to see
    if a newer release is available.
    """
    return {"version": APP_VERSION, "frozen": getattr(sys, "frozen", False)}


# GITHUB_REPO must match "owner/repo" exactly for the update-check to
# work — set via env var so this code never needs a hardcoded fork.
_GITHUB_REPO = os.environ.get("GITHUB_REPO", "").strip()


@app.get("/api/version/check")
def check_for_update():
    """
    Checks GitHub's release API for a newer version than what's
    currently running. This is the endpoint other client systems
    should poll (e.g. daily) to implement auto-update: if
    update_available is true, download_url points directly at the
    matching-platform executable attached to that release.

    Deliberately uses GitHub's own /releases/latest endpoint rather
    than a custom version server — it's free, already reliable, and
    one less thing this project has to host and keep alive.
    """
    if not _GITHUB_REPO:
        return {
            "current_version": APP_VERSION,
            "update_available": None,
            "detail": "GITHUB_REPO env var not set on this server — cannot check for updates. "
                      "Set it to 'owner/repo' to enable this endpoint.",
        }
    try:
        import requests
        resp = requests.get(
            f"https://api.github.com/repos/{_GITHUB_REPO}/releases/latest",
            timeout=8, headers={"Accept": "application/vnd.github+json"},
        )
        resp.raise_for_status()
        data = resp.json()
        latest_tag = data.get("tag_name", "").lstrip("v")
        assets = [
            {"name": a["name"], "download_url": a["browser_download_url"], "size_bytes": a["size"]}
            for a in data.get("assets", [])
        ]

        def _parse(v):
            try:
                return tuple(int(p) for p in v.split("."))
            except Exception:
                return (0, 0, 0)

        update_available = _parse(latest_tag) > _parse(APP_VERSION) if latest_tag else False

        return {
            "current_version": APP_VERSION,
            "latest_version": latest_tag or None,
            "update_available": update_available,
            "release_notes_url": data.get("html_url"),
            "assets": assets,
        }
    except Exception as e:
        return {
            "current_version": APP_VERSION,
            "update_available": None,
            "detail": f"Could not reach GitHub to check for updates: {e}",
        }


@app.get("/api/ping")
def ping():
    """Lightweight endpoint for UptimeRobot / self-ping keep-alive."""
    return {"ok": True, "ts": datetime.now().isoformat()}


@app.get("/api/system-status")
def system_status():
    """
    Real operational status per subsystem — not a pulse check. Reports
    what's actually configured and reachable so a deploy can be
    verified in one call instead of clicking through every page.
    Intended for production monitoring / post-deploy smoke checks.
    """
    status = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "core": {"status": "ok", "detail": "NSE ticker universe and local CSV data loaded"},
    }

    # Local data layer — always should work, no network dependency
    try:
        meta = get_manager().get_upload_meta()
        status["local_data"] = {
            "status": "ok" if meta.get("prices_ticker_count", 0) > 0 else "degraded",
            "prices_ticker_count": meta.get("prices_ticker_count", 0),
            "fundamentals_ticker_count": meta.get("fundamentals_ticker_count", 0),
            "detail": "OK" if meta.get("prices_ticker_count", 0) > 0 else "No price data uploaded yet — screener/scoring will run on seed data only",
        }
    except Exception as e:
        status["local_data"] = {"status": "error", "detail": str(e)}

    # Daily price snapshot job — the mechanism that accumulates real
    # NSE price history over time (no free historical source exists;
    # see CSVDataManager.snapshot_daily_prices). Runs in the
    # background at startup and every 24h; this reports whether it's
    # actually been landing rows, not just whether it exists.
    try:
        snap_meta = get_manager().get_upload_meta()
        last_snapshot = snap_meta.get("last_auto_snapshot")
        last_count = snap_meta.get("last_auto_snapshot_count", 0)
        status["daily_price_snapshot"] = {
            "status": "ok" if last_snapshot else "pending",
            "last_run": last_snapshot,
            "tickers_added_last_run": last_count,
            "detail": (
                f"Last ran {last_snapshot}, added {last_count} tickers' prices to history"
                if last_snapshot else
                "Has not run yet — runs automatically within seconds of startup, then every 24h. "
                "Technical/Capital Flow layers will start populating once ~14+ days of history accumulate."
            ),
        }
    except Exception as e:
        status["daily_price_snapshot"] = {"status": "error", "detail": str(e)}

    # Layer 1 — Global (FRED requires a key; stooq doesn't)
    fred_key_set = bool(os.environ.get("FRED_API_KEY", "").strip())
    status["layer_1_global"] = {
        "status": "ok" if fred_key_set else "partial",
        "fred_configured": fred_key_set,
        "detail": "FRED + stooq both configured" if fred_key_set else
                   "FRED_API_KEY not set — global rates/inflation/GDP/PMI unavailable; stooq (VIX/gold/oil/etc.) still works",
    }

    # Layer 2 — Country (World Bank, keyless — always "configured", live-reachability unknown until called)
    status["layer_2_country"] = {"status": "ok", "detail": "World Bank API — keyless, no configuration needed"}

    # Layer 3/4 — Sector (stooq, keyless)
    status["layer_3_4_sector"] = {"status": "ok", "detail": "stooq sector ETFs — keyless, no configuration needed"}

    # Layer 12 — Continuous learning data volume
    try:
        hist = get_recommendation_history()
        evaluated = [h for h in hist if h.get("outcome_return_pct") not in (None, "")]
        status["layer_12_continuous_learning"] = {
            "status": "ok",
            "total_logged": len(hist),
            "total_evaluated": len(evaluated),
            "detail": "Adaptive weighting active" if len(evaluated) >= 20 else
                       f"Using static weights — {len(evaluated)}/20 minimum evaluated recommendations for adaptive weighting",
        }
    except Exception as e:
        status["layer_12_continuous_learning"] = {"status": "error", "detail": str(e)}

    # CORS configuration sanity check — flag if still on permissive defaults in what looks like production
    is_render = bool(os.environ.get("RENDER", "") or os.environ.get("PORT", "") not in ("", "8000"))
    status["security"] = {
        "status": "ok" if _allowed_origins_env else ("warning" if is_render else "ok"),
        "allowed_origins_configured": bool(_allowed_origins_env),
        "detail": "ALLOWED_ORIGINS explicitly set" if _allowed_origins_env else
                   "ALLOWED_ORIGINS not set — using local-dev-only defaults. Set this env var on your deployed backend or the hosted frontend will be blocked by CORS.",
    }

    overall_ok = all(s.get("status") in ("ok", "partial") for k, s in status.items() if isinstance(s, dict) and "status" in s)
    status["overall"] = "operational" if overall_ok else "degraded"
    return status


# ── Tickers & Sectors ──────────────────────────────────────────────────────

@app.get("/api/tickers")
def get_tickers():
    return {"tickers": NSE_TICKERS}

@app.get("/api/sectors")
def get_sectors():
    sectors = sorted(set(t["sector"] for t in NSE_TICKERS))
    return {"sectors": sectors}


# ── Stocks ─────────────────────────────────────────────────────────────────

@app.get("/api/stocks")
def get_stocks(sector: str = "", sort: str = "score"):
    global _score_cache
    tickers = NSE_TICKERS
    if sector:
        tickers = [t for t in NSE_TICKERS if t["sector"].lower() == sector.lower()]

    def _process_one(meta):
        ticker = meta["ticker"]
        try:
            prices       = loader.get_price_data(ticker)
            fundamentals = loader.get_fundamentals(ticker)
            scores       = scorer.compute_scores(prices, fundamentals)
            _score_cache[ticker] = scores

            current_price = float(prices["close"].iloc[-1]) if not prices.empty else 0
            sparkline     = [_clean(p) or 0 for p in prices["close"].tail(10).tolist()] if not prices.empty else []

            total_assets = _clean(fundamentals.get("total_assets"))
            market_cap   = _clean(fundamentals.get("market_cap"))
            asset_cov    = round(total_assets / market_cap, 2) if (total_assets and market_cap and market_cap > 0) else None

            return {
                "ticker":  ticker,
                "name":    meta["name"],
                "sector":  meta["sector"],
                "scores":  _clean_dict(scores),
                "metrics": {
                    "pe":             _clean(fundamentals.get("pe")),
                    "pb":             _clean(fundamentals.get("pb")),
                    "dividend_yield": _clean(fundamentals.get("dividend_yield")),
                    "price":          round(current_price, 2),
                    "asset_coverage": asset_cov,
                    "data_stale":     bool(fundamentals.get("data_stale")),
                    "last_update":    fundamentals.get("last_update", ""),
                },
                "sparkline": [round(p, 2) for p in sparkline],
            }
        except Exception as e:
            print(f"[stocks] skip {ticker}: {e}")
            return None

    results = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = list(ex.map(_process_one, tickers, timeout=20))
    results = [r for r in futures if r is not None]

    if sort == "price":
        results.sort(key=lambda x: x["metrics"].get("price") or 0, reverse=True)
    elif sort == "pe":
        results.sort(key=lambda x: x["metrics"].get("pe") or 9999)
    elif sort == "pb":
        results.sort(key=lambda x: x["metrics"].get("pb") or 9999)
    elif sort == "yield":
        results.sort(key=lambda x: x["metrics"].get("dividend_yield") or 0, reverse=True)
    else:
        results.sort(key=lambda x: x["scores"].get("total_score") or 0, reverse=True)

    return {"stocks": results, "count": len(results)}


@app.get("/api/stock/{ticker}/recommendation")
def get_stock_recommendation(ticker: str):
    """Layer 10 — AI Recommendation Engine. Synthesizes company score
    (Layer 5), valuation (Layer 6), technical (Layer 8), capital flow
    (Layer 7), and NSE sector momentum (Layer 3/4) into one transparent,
    reproducible recommendation with an explainable thesis."""
    ticker = ticker.upper()
    if "." not in ticker:
        ticker += ".NR"
    try:
        meta = next((t for t in NSE_TICKERS if t["ticker"] == ticker.split(".")[0]), None)
        if not meta:
            raise HTTPException(status_code=404, detail=f"Unknown ticker {ticker}")

        prices = loader.get_price_data(ticker)
        fundamentals = loader.get_fundamentals(ticker)
        scores = scorer.compute_scores(prices, fundamentals)

        fund_with_price = dict(fundamentals)
        if prices is not None and not prices.empty:
            fund_with_price["price"] = float(prices["close"].iloc[-1])
        valuation = compute_valuation(fund_with_price)
        technical = compute_technical(prices)
        capital_flow = compute_capital_flow(prices)

        sector_intel = compute_sector_industry_intelligence(NSE_TICKERS, loader)
        nse_sector_data = sector_intel.get("nse_sectors")

        current_price = fund_with_price.get("price")

        # Layer 12 feedback loop: use real historical performance to
        # adjust component weights, gated by sample size so it can't
        # overfit on thin data. Falls back to static weights until
        # enough evaluated recommendations exist.
        effectiveness = get_component_effectiveness()
        adaptive = compute_adaptive_weights(effectiveness)

        rec = synthesize_recommendation(
            ticker=ticker, name=meta["name"], sector_name=meta["sector"],
            company_scores=scores, valuation=valuation, technical=technical,
            capital_flow=capital_flow, nse_sector_data=nse_sector_data,
            current_price=current_price, weights=adaptive["weights"],
        )
        if rec.get("available"):
            rec["weight_adaptation"] = {
                "adaptive": adaptive["adaptive"],
                "reason": adaptive["reason"],
                "adjustments_applied": adaptive.get("adjustments_applied", {}),
            }
        return rec
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@app.get("/api/stock/{ticker_raw:path}")
def get_stock(ticker_raw: str):
    try:
        ticker = ticker_raw.upper()
        if "." not in ticker:
            ticker = ticker + ".NR"

        prices       = loader.get_price_data(ticker)
        fundamentals = loader.get_fundamentals(ticker)
        scores       = scorer.compute_scores(prices, fundamentals)
        position     = portfolio.get_position(ticker)
        watchlist    = loader.get_watchlist()
        missing      = loader.get_missing_fields(ticker, fundamentals)

        price_history = []
        if not prices.empty:
            for dt, row in prices.tail(365).iterrows():
                try:
                    price_history.append({
                        "date":   str(dt.date() if hasattr(dt, "date") else dt),
                        "open":   round(_clean(row["open"]) or 0, 2),
                        "high":   round(_clean(row["high"]) or 0, 2),
                        "low":    round(_clean(row["low"])  or 0, 2),
                        "close":  round(_clean(row["close"]) or 0, 2),
                        "volume": int(row["volume"]) if not math.isnan(float(row["volume"])) else 0,
                    })
                except Exception:
                    continue

        meta = next((s for s in NSE_TICKERS if s["ticker"] == ticker.split(".")[0]),
                    {"name": ticker, "sector": "Unknown"})

        rev_history = fundamentals.get("revenue_history", [])
        ni_history  = fundamentals.get("net_income_history", [])
        dps_history = fundamentals.get("dps_history", [])
        current_year = datetime.now().year
        years = list(range(current_year - len(rev_history) + 1, current_year + 1)) if rev_history else []

        # Layer 8 — Technical Intelligence (pure computation on price history)
        try:
            technical = compute_technical(prices)
        except Exception as e:
            technical = {"available": False, "reason": f"technical calc error: {e}"}

        # Layer 6 ext — DCF / DDM / margin of safety (needs current price injected,
        # same pattern scoring.py already uses)
        try:
            fund_with_price = dict(fundamentals)
            if not prices.empty:
                fund_with_price["price"] = float(prices["close"].iloc[-1])
            valuation = compute_valuation(fund_with_price)
        except Exception as e:
            valuation = {"error": f"valuation calc error: {e}"}

        # Layer 7 — Capital Flow Engine (volume-based accumulation/distribution)
        try:
            capital_flow = compute_capital_flow(prices)
        except Exception as e:
            capital_flow = {"available": False, "reason": f"capital flow calc error: {e}"}

        return {
            "ticker":        ticker,
            "name":          meta["name"],
            "sector":        meta["sector"],
            "scores":        _clean_dict(scores),
            "price_history": price_history,
            "fundamentals": {
                "eps":       _clean(fundamentals.get("eps")),
                "bvps":      _clean(fundamentals.get("bvps")),
                "revenue":   _clean(fundamentals.get("revenue")),
                "debt":      _clean(fundamentals.get("debt")),
                "dividends": _clean(fundamentals.get("dividends")),
                "roe":       _clean(fundamentals.get("roe")),
                "margin":    _clean(fundamentals.get("margin")),
                "pe":        _clean(fundamentals.get("pe")),
                "pb":        _clean(fundamentals.get("pb")),
                "debt_to_equity":    _clean(fundamentals.get("debt_to_equity")),
                "interest_coverage": _clean(fundamentals.get("interest_coverage")),
                "total_assets":      _clean(fundamentals.get("total_assets")),
                "market_cap":        _clean(fundamentals.get("market_cap")),
                "dividend_yield":    _clean(fundamentals.get("dividend_yield")),
            },
            "history_charts": {
                "years":      years,
                "revenue":    [_clean(v) for v in rev_history],
                "net_income": [_clean(v) for v in ni_history],
                "dividends":  [_clean(v) for v in dps_history],
            },
            "my_position":   position,
            "in_watchlist":  ticker in watchlist,
            "missing_fields": missing,
            "technical":     technical,
            "valuation":     valuation,
            "capital_flow":  capital_flow,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── CSV Upload endpoints ───────────────────────────────────────────────────

@app.get("/api/template/prices")
def download_price_template():
    """Download CSV template for price upload — all NSE tickers pre-filled."""
    csv_content = generate_price_template(NSE_TICKERS)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=nse_prices_template.csv"}
    )

@app.get("/api/template/fundamentals")
def download_fundamentals_template():
    """Download CSV template for fundamentals — pre-filled from seed data."""
    from services.data_loader import _load_seed
    seed = _load_seed()
    csv_content = generate_fundamentals_template(NSE_TICKERS, seed)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=nse_fundamentals_template.csv"}
    )

@app.post("/api/upload/prices")
async def upload_prices(file: UploadFile = File(...)):
    """
    Upload price CSV.
    - Must have columns: ticker, date, close (open/high/low/volume optional)
    - Merges with existing data — no data loss
    - Warns if prices are stale
    """
    try:
        content = await file.read()
        mgr = get_manager()
        result = mgr.upload_prices(content)
        if not result["success"] and result.get("errors"):
            raise HTTPException(status_code=400, detail="\n".join(result["errors"]))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload/fundamentals")
async def upload_fundamentals(file: UploadFile = File(...)):
    """
    Upload fundamentals CSV.
    - Must have: ticker + at least one of eps/pe/roe/bvps
    - Merges per field — existing data preserved for empty fields
    - No data loss
    """
    try:
        content = await file.read()
        mgr = get_manager()
        result = mgr.upload_fundamentals(content)
        if not result["success"] and result.get("errors"):
            raise HTTPException(status_code=400, detail="\n".join(result["errors"]))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/upload/status")
def upload_status():
    """Returns metadata about last uploads — timestamps, counts, staleness."""
    mgr = get_manager()
    meta = mgr.get_upload_meta()
    price_age  = mgr.get_prices_age_days()
    fund_age   = mgr.get_fundamentals_age_days()
    return {
        "prices": {
            "last_upload":   meta.get("prices_last_upload", "never"),
            "ticker_count":  meta.get("prices_ticker_count", 0),
            "age_days":      round(price_age, 1),
            "status":        "ok" if price_age < 7 else "stale" if price_age < 14 else "critical",
        },
        "fundamentals": {
            "last_upload":   meta.get("fundamentals_last_upload", "never"),
            "ticker_count":  meta.get("fundamentals_ticker_count", 0),
            "age_days":      round(fund_age, 1),
            "status":        "ok" if fund_age < 90 else "stale",
        },
    }


# ── Data freshness & health ────────────────────────────────────────────────

@app.get("/api/data-freshness")
def data_freshness():
    try:
        return {"freshness": loader.get_data_freshness(NSE_TICKERS)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/data-health")
def data_health():
    """Returns actionable alerts for the notification bell."""
    try:
        mgr = get_manager()
        alerts = mgr.get_health_alerts(NSE_TICKERS)
        return {"alerts": alerts, "count": len(alerts)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/data-sources")
def data_sources():
    """Returns current data source info."""
    try:
        mgr = get_manager()
        meta = mgr.get_upload_meta()
        return {
            "mode": "manual_csv",
            "prices_last_upload": meta.get("prices_last_upload", "never"),
            "fundamentals_last_upload": meta.get("fundamentals_last_upload", "never"),
            "prices_count": meta.get("prices_ticker_count", 0),
            "fundamentals_count": meta.get("fundamentals_ticker_count", 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Manual single-field entry (existing feature) ──────────────────────────

@app.post("/api/missing-data")
def save_missing_data(req: MissingDataRequest):
    try:
        ticker = req.ticker.upper()
        try:
            val = float(req.value)
        except ValueError:
            val = req.value
        loader.save_missing_field(ticker, req.field_name, val, req.source)
        prices       = loader.get_price_data(ticker)
        fundamentals = loader.get_fundamentals(ticker)
        scores       = scorer.compute_scores(prices, fundamentals)
        _score_cache[ticker] = scores
        return {"success": True, "new_scores": _clean_dict(scores)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/manual-price")
def manual_price(req: ManualPriceRequest):
    """Set a single ticker's price manually."""
    try:
        from io import BytesIO
        import csv
        ticker = req.ticker.upper().split(".")[0]
        date   = req.date or datetime.now().strftime("%Y-%m-%d")
        csv_str = f"ticker,date,open,high,low,close,volume\n{ticker},{date},{req.price},{req.price},{req.price},{req.price},0\n"
        mgr = get_manager()
        result = mgr.upload_prices(csv_str.encode())
        return {"success": True, "ticker": ticker, "price": req.price}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/manual-fundamental")
def manual_fundamental(req: ManualFundamentalRequest):
    """Set a single fundamental field for a ticker."""
    try:
        ticker = req.ticker.upper().split(".")[0]
        loader.save_missing_field(ticker, req.field, req.value, "manual_entry")
        return {"success": True, "ticker": ticker, "field": req.field, "value": req.value}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Portfolio ──────────────────────────────────────────────────────────────

def _enrich(summary: dict) -> dict:
    total_invested = 0.0
    current_value  = 0.0
    realized_total = 0.0
    enriched = []

    holdings = summary.get("holdings", [])
    total_value_all = sum(
        h.get("current_price", 0) * h.get("quantity", 0) for h in holdings
    )

    for h in holdings:
        ticker   = h["ticker"]
        avg_cost = h["avg_cost"]
        qty      = h["quantity"]

        try:
            prices = loader.get_price_data(ticker)
            cp = float(prices["close"].iloc[-1]) if not prices.empty else avg_cost
        except Exception:
            cp = avg_cost

        cp = _clean(cp) or avg_cost
        bp_score = None
        if ticker in _score_cache:
            ts = _score_cache[ticker].get("total_score")
            bp_score = ts if ts is not None else None

        unr = round((cp - avg_cost) * qty, 2)
        position_value = cp * qty
        alloc_pct = round(position_value / total_value_all * 100, 1) if total_value_all > 0 else 0

        total_invested += avg_cost * qty
        current_value  += cp * qty
        realized_total += h.get("realized_pl", 0)

        enriched.append({
            "ticker":             ticker,
            "quantity":           qty,
            "avg_cost":           round(avg_cost, 2),
            "current_price":      round(cp, 2),
            "unrealized_pl":      unr,
            "realized_pl":        round(h.get("realized_pl", 0), 2),
            "dividends_received": round(h.get("dividends_received", 0), 2),
            "holding_days":       h.get("holding_days", 0),
            "total_score":        bp_score,
            "allocation_pct":     alloc_pct,
        })

    unr_total  = current_value - total_invested
    return_pct = unr_total / total_invested if total_invested > 0 else 0.0

    scored = [h["total_score"] for h in enriched if h["total_score"] is not None]
    avg_score = round(sum(scored) / len(scored), 1) if scored else None

    if enriched:
        avg_days = sum(h["holding_days"] for h in enriched) / len(enriched)
        years = max(avg_days / 365, 0.001)
        ann_return = ((1 + return_pct) ** (1 / years)) - 1 if return_pct > -1 else -1
    else:
        ann_return = 0.0

    dividends_total = sum(h.get("dividends_received", 0) for h in enriched)

    return {
        "summary": {
            "total_invested":    round(total_invested, 2),
            "current_value":     round(current_value, 2),
            "unrealized_pl":     round(unr_total, 2),
            "realized_pl":       round(realized_total, 2),
            "return_pct":        round(return_pct, 4),
            "annualized_return": round(ann_return, 4),
            "dividends_ytd":     round(dividends_total, 2),
            "avg_score":         avg_score,
        },
        "holdings": enriched,
    }


def _build_benchmark_basket() -> list:
    """
    Equal-weighted basket of all tracked NSE tickers as a market proxy
    for beta calculations (Layer 9). No free, reliable NASI index feed
    is wired up yet — this is an explicit, declared approximation, not
    a substitute for real index data (see risk.py docstring).
    Returns a chronological list of basket index values (base = 100).
    """
    series_list = []
    for t in NSE_TICKERS:
        try:
            df = loader.get_price_data(t["ticker"])
            if df is not None and not df.empty and len(df) >= 10:
                s = df["close"].astype(float)
                s.index = pd.to_datetime(s.index).normalize()
                series_list.append(s / s.iloc[0] * 100)  # normalize to common base
        except Exception:
            continue

    if len(series_list) < 2:
        return []

    combined = pd.concat(series_list, axis=1).sort_index().ffill()
    basket = combined.mean(axis=1, skipna=True).dropna()
    return basket.tolist()


@app.get("/api/portfolio")
def get_portfolio():
    try:
        return _enrich(portfolio.get_summary(loader))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Layers 1-4: Global / Country / Sector / Industry Intelligence ───────
# Cached at module level (separate from the per-function caches inside
# macro.py/country.py/sector.py) so concurrent requests during a burst
# don't each trigger their own external fetch storm.
_layer1234_cache = {"global": None, "global_ts": 0, "country": None, "country_ts": 0,
                     "sector": None, "sector_ts": 0}
_LAYER_CACHE_TTL = 1800  # 30 min


@app.get("/api/intelligence/global")
def get_global_layer():
    """Layer 1 — Global Intelligence Engine (FRED + stooq)."""
    now = time.time()
    if _layer1234_cache["global"] and (now - _layer1234_cache["global_ts"]) < _LAYER_CACHE_TTL:
        return _layer1234_cache["global"]
    try:
        result = compute_global_intelligence()
        _layer1234_cache["global"] = result
        _layer1234_cache["global_ts"] = now
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/intelligence/country")
def get_country_layer(countries: str = None):
    """Layer 2 — Country Intelligence Engine (World Bank).
    Optional ?countries=KEN,USA,GBR to override the default tracked list."""
    codes = [c.strip().upper() for c in countries.split(",")] if countries else None
    cache_key = countries or "default"
    now = time.time()
    cached = _layer1234_cache.get("country")
    if cached and cached.get("_cache_key") == cache_key and (now - _layer1234_cache["country_ts"]) < _LAYER_CACHE_TTL:
        return cached
    try:
        result = compute_country_intelligence(codes)
        result["_cache_key"] = cache_key
        _layer1234_cache["country"] = result
        _layer1234_cache["country_ts"] = now
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/intelligence/sector")
def get_sector_layer():
    """Layers 3+4 — Sector + Industry Intelligence (global ETF rotation
    via stooq, plus NSE-local sector momentum from your own price data)."""
    now = time.time()
    if _layer1234_cache["sector"] and (now - _layer1234_cache["sector_ts"]) < _LAYER_CACHE_TTL:
        return _layer1234_cache["sector"]
    try:
        result = compute_sector_industry_intelligence(NSE_TICKERS, loader)
        _layer1234_cache["sector"] = result
        _layer1234_cache["sector_ts"] = now
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/portfolio/risk")
def get_portfolio_risk():
    """Layer 9 (Risk) + Layer 11 (Portfolio Intelligence):
    Sharpe, Sortino, max drawdown, beta, correlation matrix,
    diversification (HHI), and portfolio health score."""
    try:
        equity_curve = analytics.get_equity_curve(portfolio, loader)

        holdings = portfolio.get_summary(loader).get("holdings", [])
        price_series_by_ticker = {}
        for h in holdings:
            ticker = h["ticker"]
            try:
                df = loader.get_price_data(ticker)
                if df is not None and not df.empty:
                    s = df["close"].astype(float)
                    s.index = pd.to_datetime(s.index).normalize()
                    price_series_by_ticker[ticker] = s
            except Exception:
                price_series_by_ticker[ticker] = None

        benchmark_values = _build_benchmark_basket()
        sector_by_ticker = {t["ticker"]: t["sector"] for t in NSE_TICKERS}

        risk = compute_portfolio_risk(
            equity_curve=equity_curve,
            price_series_by_ticker=price_series_by_ticker,
            benchmark_values=benchmark_values,
            holdings=holdings,
            sector_by_ticker=sector_by_ticker,
        )
        return risk
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/recommendations/log")
def log_recommendation_endpoint(ticker: str):
    """Layer 12 — snapshot a Layer 10 recommendation for future outcome tracking."""
    try:
        rec = get_stock_recommendation(ticker)
        if not rec.get("available"):
            raise HTTPException(status_code=400, detail="No recommendation available to log")
        rec_id = log_recommendation(ticker, {
            "company_score": rec["component_scores"].get("company"),
            "valuation_score": rec["component_scores"].get("valuation"),
            "technical_score": rec["component_scores"].get("technical"),
            "capital_flow_score": rec["component_scores"].get("capital_flow"),
            "sector_score": rec["component_scores"].get("sector"),
            "risk_classification": None,
            "overall_recommendation": rec["recommendation"],
            "confidence": rec["confidence"],
            "price_at_recommendation": rec.get("current_price"),
            "thesis_summary": rec["thesis"]["summary"],
        })
        return {"success": True, "recommendation_id": rec_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/recommendations/{recommendation_id}/outcome")
def record_recommendation_outcome(recommendation_id: str, current_price: float):
    """Layer 12 — backfill the actual outcome for a past logged recommendation."""
    try:
        result = record_outcome(recommendation_id, current_price)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("reason"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/recommendations/history")
def get_recommendations_history(ticker: str = None):
    """Layer 12 — recommendation log, optionally filtered by ticker."""
    try:
        return {"history": get_recommendation_history(ticker)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/recommendations/accuracy")
def get_recommendations_accuracy():
    """Layer 12 — aggregate accuracy stats across all recommendations
    with recorded outcomes. Empty/low-confidence until months of
    history accumulate — this is expected, not a bug."""
    try:
        return get_accuracy_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/recommendations/effectiveness")
def get_recommendations_effectiveness():
    """Layer 12 — the actual feedback loop. Shows how strongly each
    Layer 10 component (company, valuation, technical, capital flow,
    sector) has historically correlated with real outcomes, and
    whether there's enough evaluated history to trust that correlation.
    This is what /api/stock/{ticker}/recommendation's weight_adaptation
    field is built from — inspect this if a recommendation's weights
    look unexpected."""
    try:
        return get_component_effectiveness()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trades")
def add_trade(trade: TradeRequest):
    try:
        ticker = trade.ticker.upper()
        if "." not in ticker:
            ticker = ticker + ".NR"
        portfolio.add_trade(
            ticker=ticker,
            trade_type=trade.trade_type.upper(),
            quantity=trade.quantity,
            price=trade.price,
            date=trade.date,
        )
        return _enrich(portfolio.get_summary(loader))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analytics")
def get_analytics():
    try:
        return analytics.get_analytics(portfolio, loader, scorer, NSE_TICKERS)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Watchlist ──────────────────────────────────────────────────────────────

@app.get("/api/watchlist")
def get_watchlist():
    wl = loader.get_watchlist()
    return {"watchlist": wl}

@app.post("/api/watchlist/add")
def add_watchlist(req: WatchlistRequest):
    ticker = req.ticker.upper()
    if "." not in ticker:
        ticker += ".NR"
    wl = loader.add_to_watchlist(ticker)
    return {"watchlist": wl}

@app.post("/api/watchlist/remove")
def remove_watchlist(req: WatchlistRequest):
    ticker = req.ticker.upper()
    if "." not in ticker:
        ticker += ".NR"
    wl = loader.remove_from_watchlist(ticker)
    return {"watchlist": wl}


# ── Bundled frontend (only present in the packaged executable) ──────────
# Mounted LAST, deliberately — StaticFiles' catch-all must never be able
# to shadow an /api/* route. In normal local dev (npm run dev on its own
# port) this directory won't exist and the mount is silently skipped;
# only the PyInstaller build ships frontend/dist alongside the exe.
_static_dir = _app_base_path() / "frontend" / "dist"
if _static_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(_static_dir / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        """Single-page-app fallback: any non-API, non-asset path
        serves index.html so React Router-style client-side routing
        works even on a hard refresh of a deep link.
        Deliberately excludes /api/* — an unmatched API path must
        still 404 normally, never silently fall through to HTML.
        Without this check, a typo'd or removed API route would
        return 200 + index.html instead of a real 404, masking
        errors from any client integration checking status codes."""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail=f"Not found: /{full_path}")
        requested = _static_dir / full_path
        if full_path and requested.exists() and requested.is_file():
            return FileResponse(requested)
        return FileResponse(_static_dir / "index.html")


def _open_browser_when_ready(port: int, timeout_seconds: int = 30):
    """
    Waits for the server to actually be accepting connections, then
    opens the default browser to it — automatically, once. A client
    running a double-clicked .exe should never have to know the app
    talks over localhost:8000 or manually type a URL; the app should
    just appear, the way any normal desktop application does.
    Runs in a background thread so it never blocks server startup.
    """
    import webbrowser
    import urllib.request

    def _wait_and_open():
        url = f"http://localhost:{port}"
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f"{url}/api/ping", timeout=1)
                webbrowser.open(url)
                return
            except Exception:
                time.sleep(0.5)
        # Timed out waiting — don't silently fail the whole app over
        # this; the user can still open the URL manually, and the
        # console banner already told them what it is.
        print(f"[stockintel] Could not auto-open browser — please open {url} manually.")

    threading.Thread(target=_wait_and_open, daemon=True).start()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    is_frozen = getattr(sys, "frozen", False)
    # Reload mode re-imports the app by module string ("app:app"),
    # which works from source but breaks inside a PyInstaller-frozen
    # executable — there's no "app.py" file on disk to re-import, only
    # the bundled archive. Auto-reload only makes sense in dev anyway,
    # so it's forced off whenever running as a packaged executable,
    # and the app object is passed directly (not by string) in that
    # case to avoid the same import-by-string failure mode entirely.
    reload = (not is_frozen) and os.environ.get("ENVIRONMENT", "development") == "development"
    if is_frozen:
        # A client running this .exe is not a developer — they should
        # see a short, friendly banner and their browser opening, not
        # raw internal startup logs or a bare console full of uvicorn
        # access-log lines for every request. log_level="warning"
        # suppresses the per-request noise; errors still show if
        # something genuinely breaks.
        print("=" * 50)
        print(f"  Stock Intel v{APP_VERSION}")
        print("=" * 50)
        print(f"  Starting up... your browser will open automatically.")
        print(f"  If it doesn't, go to: http://localhost:{port}")
        print(f"  Close this window to stop the app.")
        print("=" * 50)
        _open_browser_when_ready(port)
        uvicorn.run(app, host="0.0.0.0", port=port, reload=False, log_level="warning")
    else:
        uvicorn.run("app:app", host="0.0.0.0", port=port, reload=reload)
