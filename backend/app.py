"""
Stock Intel API — FastAPI backend
Manual CSV data uploads. No scraping. No external APIs.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn, math, threading, os, time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from services.data_loader import DataLoader
from services.scoring import ScoringEngine
from services.portfolio import PortfolioManager
from services.analytics import AnalyticsEngine
from services.csv_data_manager import get_manager, generate_price_template, generate_fundamentals_template

# ── Keep-alive: robust external ping via UptimeRobot or self-ping ──────────
def _start_keep_alive():
    """
    Two-layer keep-alive for Render free tier:
    1. Self-ping every 14 min (keeps process warm between external pings)
    2. Designed to work WITH UptimeRobot free plan pinging /api/ping every 5 min
    
    Set RENDER_EXTERNAL_URL env var in Render dashboard to enable self-ping.
    Also add UptimeRobot monitor: https://your-app.onrender.com/api/ping
    """
    def _loop():
        time.sleep(90)  # wait for startup
        self_url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
        if not self_url:
            print("[keep-alive] RENDER_EXTERNAL_URL not set — add it in Render env vars")
            return
        ping_url = f"{self_url}/api/ping"
        print(f"[keep-alive] Self-ping every 14 min → {ping_url}")
        while True:
            try:
                import requests as _req
                r = _req.get(ping_url, timeout=15)
                print(f"[keep-alive] ✓ {r.status_code} at {datetime.now().strftime('%H:%M:%S')}")
            except Exception as e:
                print(f"[keep-alive] ✗ ping failed: {e}")
            time.sleep(14 * 60)
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
    print("[startup] Ready.")
    yield

app = FastAPI(title="Stock Intel API", version="5.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

@app.get("/api/ping")
def ping():
    """Lightweight endpoint for UptimeRobot / self-ping keep-alive."""
    return {"ok": True, "ts": datetime.now().isoformat()}


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
        current_year = 2024
        years = list(range(current_year - len(rev_history) + 1, current_year + 1)) if rev_history else []

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


@app.get("/api/portfolio")
def get_portfolio():
    try:
        return _enrich(portfolio.get_summary(loader))
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


# ══════════════════════════════════════════════════════════════════════════
# GOLD MODULE — unchanged
# ══════════════════════════════════════════════════════════════════════════

from services.gold import (
    fetch_live_price, fetch_ohlcv, generate_signal,
    run_backtest, demo_manager, compute_indicators,
    support_resistance, fibonacci_levels
)

class DemoTradeRequest(BaseModel):
    direction: str
    entry: float
    sl: float
    tp1: float
    tp2: float
    score: int
    lot_size: float = 0.1

class CloseTradeRequest(BaseModel):
    trade_id: int
    close_price: float
    result: str

class BacktestRequest(BaseModel):
    interval: str = "1h"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    atr_sl_mult: float = 1.5
    atr_tp_mult: float = 4.5
    min_score: int = 35


@app.get("/api/gold/price")
def gold_price():
    try:
        return fetch_live_price()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/gold/candles")
def gold_candles(interval: str = "1h", outputsize: int = 300):
    try:
        df = fetch_ohlcv(interval=interval, outputsize=outputsize)
        if df.empty:
            return {"candles": [], "interval": interval}
        df = compute_indicators(df)
        records = []
        for dt, row in df.iterrows():
            records.append({
                "datetime": str(dt),
                "open":   round(_clean(row["open"]) or 0, 2),
                "high":   round(_clean(row["high"]) or 0, 2),
                "low":    round(_clean(row["low"])  or 0, 2),
                "close":  round(_clean(row["close"]) or 0, 2),
                "volume": round(_clean(row.get("volume", 0)) or 0, 2),
                "ema9":   round(_clean(row.get("ema9"))  or 0, 2),
                "ema21":  round(_clean(row.get("ema21")) or 0, 2),
                "ema50":  round(_clean(row.get("ema50")) or 0, 2),
                "ema200": round(_clean(row.get("ema200")) or 0, 2),
                "rsi":    round(_clean(row.get("rsi14")) or 0, 1),
                "macd_hist": round(_clean(row.get("macd_hist")) or 0, 4),
                "atr":    round(_clean(row.get("atr14")) or 0, 2),
            })
        return {"candles": records, "interval": interval, "count": len(records)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/gold/signal")
def gold_signal():
    try:
        df_h4  = fetch_ohlcv(interval="4h",    outputsize=500)
        df_h1  = fetch_ohlcv(interval="1h",    outputsize=300)
        df_m30 = fetch_ohlcv(interval="30min", outputsize=200)
        signal = generate_signal(df_h4, df_h1, df_m30)
        return signal
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/gold/backtest")
def gold_backtest(req: BacktestRequest):
    try:
        df = fetch_ohlcv(interval=req.interval, outputsize=1000)
        if df.empty:
            raise HTTPException(status_code=400, detail="No price data available for backtest")
        result = run_backtest(df, start_date=req.start_date, end_date=req.end_date,
                              atr_sl_mult=req.atr_sl_mult, atr_tp_mult=req.atr_tp_mult,
                              min_score=req.min_score)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/gold/demo/trades")
def get_demo_trades():
    try:
        return {"trades": demo_manager.get_trades(), "performance": demo_manager.get_performance()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/gold/demo/open")
def open_demo_trade(req: DemoTradeRequest):
    try:
        trade = demo_manager.open_trade(
            direction=req.direction, entry=req.entry,
            sl=req.sl, tp1=req.tp1, tp2=req.tp2,
            score=req.score, lot_size=req.lot_size)
        return {"trade": trade, "performance": demo_manager.get_performance()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/gold/demo/close")
def close_demo_trade(req: CloseTradeRequest):
    try:
        trades = demo_manager.close_trade(req.trade_id, req.close_price, req.result)
        return {"trades": trades, "performance": demo_manager.get_performance()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/gold/sr-fib")
def gold_sr_fib():
    try:
        df = fetch_ohlcv(interval="4h", outputsize=300)
        if df.empty:
            return {"sr": {}, "fib": {}}
        sr  = support_resistance(df, lookback=100)
        fib = fibonacci_levels(df, lookback=200)
        return {"sr": sr, "fib": fib}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    reload = os.environ.get("ENVIRONMENT", "development") == "development"
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=reload)
