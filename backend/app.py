"""
Stock Intel API — FastAPI backend (full spec implementation)
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi import BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import uvicorn
import math
import threading
from concurrent.futures import ThreadPoolExecutor

from services.data_loader import DataLoader
from services.scoring import ScoringEngine
from services.portfolio import PortfolioManager
from services.analytics import AnalyticsEngine

app = FastAPI(title="Stock Intel API", version="3.0.0")

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

# ── Startup: kick off background prefetch so app is ready fast ─────────────
@app.on_event("startup")
def startup_prefetch():
    def _bg():
        loader.prefetch_all(NSE_TICKERS)
    threading.Thread(target=_bg, daemon=True).start()
    print("[startup] Background prefetch started for all NSE tickers.")

# Full NSE ticker list
NSE_TICKERS = [
    # Banking
    {"ticker": "EQTY.NR", "name": "Equity Group Holdings",    "sector": "Banking"},
    {"ticker": "KCB.NR",  "name": "KCB Group",                "sector": "Banking"},
    {"ticker": "COOP.NR", "name": "Co-operative Bank",        "sector": "Banking"},
    {"ticker": "ABSA.NR", "name": "ABSA Bank Kenya",          "sector": "Banking"},
    {"ticker": "NCBA.NR", "name": "NCBA Group",               "sector": "Banking"},
    {"ticker": "DTK.NR",  "name": "Diamond Trust Bank",       "sector": "Banking"},
    {"ticker": "SCBK.NR", "name": "Standard Chartered Kenya", "sector": "Banking"},
    {"ticker": "I&M.NR",  "name": "I&M Group",                "sector": "Banking"},
    {"ticker": "HF.NR",   "name": "HF Group",                 "sector": "Banking"},
    {"ticker": "SBIC.NR", "name": "Stanbic Holdings",         "sector": "Banking"},
    # Telecom
    {"ticker": "SCOM.NR", "name": "Safaricom PLC",            "sector": "Telecom"},
    # Consumer
    {"ticker": "EABL.NR", "name": "East African Breweries",   "sector": "Consumer"},
    {"ticker": "BAT.NR",  "name": "BAT Kenya",                "sector": "Consumer"},
    {"ticker": "UNGA.NR", "name": "Unga Group",               "sector": "Consumer"},
    {"ticker": "KCGM.NR", "name": "Kenya Grange Vehicle",     "sector": "Consumer"},
    # Insurance
    {"ticker": "BRIT.NR", "name": "Britam Holdings",          "sector": "Insurance"},
    {"ticker": "JUB.NR",  "name": "Jubilee Holdings",         "sector": "Insurance"},
    {"ticker": "CIC.NR",  "name": "CIC Insurance Group",      "sector": "Insurance"},
    {"ticker": "KNRE.NR", "name": "Kenya Re",                 "sector": "Insurance"},
    # Energy
    {"ticker": "TOTL.NR", "name": "TotalEnergies Kenya",      "sector": "Energy"},
    {"ticker": "KENOL.NR","name": "KenolKobil",               "sector": "Energy"},
    # Manufacturing
    {"ticker": "BAMB.NR", "name": "Bamburi Cement",           "sector": "Manufacturing"},
    {"ticker": "ARM.NR",  "name": "ARM Cement",               "sector": "Manufacturing"},
    {"ticker": "CABL.NR", "name": "East African Cables",      "sector": "Manufacturing"},
    {"ticker": "BERG.NR", "name": "Bergougnan EA",            "sector": "Manufacturing"},
    # Agriculture
    {"ticker": "SASN.NR", "name": "Sasini",                   "sector": "Agriculture"},
    {"ticker": "KAPC.NR", "name": "Kapchorua Tea",            "sector": "Agriculture"},
    {"ticker": "LIMT.NR", "name": "Limuru Tea",               "sector": "Agriculture"},
    {"ticker": "TPSE.NR", "name": "Trans-Century",            "sector": "Agriculture"},
    # Investment
    {"ticker": "CTUM.NR", "name": "Centum Investment",        "sector": "Investment"},
    {"ticker": "NSE.NR",  "name": "Nairobi Securities Exchange","sector": "Investment"},
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
    alert_type: str   # "score_above" | "score_below" | "price_drop"
    threshold: float


@app.get("/")
def root():
    return {"message": "Stock Intel API v3", "status": "running"}


@app.get("/api/tickers")
def get_tickers():
    return {"tickers": NSE_TICKERS}


@app.get("/api/sectors")
def get_sectors():
    sectors = sorted(set(t["sector"] for t in NSE_TICKERS))
    return {"sectors": sectors}


@app.get("/api/stocks")
def get_stocks(sector: str = "", sort: str = "score"):
    """
    Returns all stocks. Parallel fetch — max 8s total wait.
    Serves from cache immediately if available. Never hangs.
    """
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
                "ticker":   ticker,
                "name":     meta["name"],
                "sector":   meta["sector"],
                "scores":   _clean_dict(scores),
                "metrics": {
                    "pe":             _clean(fundamentals.get("pe")),
                    "pb":             _clean(fundamentals.get("pb")),
                    "dividend_yield": _clean(fundamentals.get("dividend_yield")),
                    "price":          round(current_price, 2),
                    "asset_coverage": asset_cov,
                    "data_stale":     bool(fundamentals.get("data_stale")),
                    "last_update":    fundamentals.get("last_update",""),
                },
                "sparkline": [round(p, 2) for p in sparkline],
            }
        except Exception as e:
            print(f"[stocks] skip {ticker}: {e}")
            return None

    results = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = list(ex.map(_process_one, tickers))
    results = [r for r in futures if r is not None]

    # Sorting
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

        meta = next((s for s in NSE_TICKERS if s["ticker"] == ticker),
                    {"name": ticker, "sector": "Unknown"})

        # Build 5-year chart data from history arrays
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

    # Average portfolio score
    scored = [h["total_score"] for h in enriched if h["total_score"] is not None]
    avg_score = round(sum(scored) / len(scored), 1) if scored else None

    # Annualised return
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


# ── Data freshness ─────────────────────────────────────────────────────────

@app.get("/api/data-freshness")
def data_freshness():
    """Returns per-ticker freshness status for the UI data tracker."""
    try:
        return {"freshness": loader.get_data_freshness(NSE_TICKERS)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/refresh-stock")
def refresh_stock(body: dict):
    """Force re-fetch a single ticker bypassing cache."""
    try:
        ticker = str(body.get("ticker","")).upper()
        if not ticker:
            raise HTTPException(status_code=400, detail="ticker required")
        base = ticker.split(".")[0]
        # Clear NSE scraper caches for this ticker
        from pathlib import Path
        import json
        cache_dir = Path(__file__).parent / "data" / "nse_cache"
        for cache_file in ["prices.json", "fundamentals.json"]:
            cp = cache_dir / cache_file
            if cp.exists():
                try:
                    with open(cp) as f: data = json.load(f)
                    data.pop(base, None)
                    with open(cp,"w") as f: json.dump(data, f, indent=2)
                except Exception: pass
        # Fetch fresh
        prices = loader.get_price_data(ticker)
        funds  = loader.get_fundamentals(ticker)
        return {
            "ticker":      ticker,
            "price_ok":    not prices.empty,
            "fund_ok":     bool(funds.get("pe") or funds.get("eps")),
            "last_update": funds.get("last_update",""),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Missing data ───────────────────────────────────────────────────────────

@app.post("/api/missing-data")
def save_missing_data(req: MissingDataRequest):
    try:
        ticker = req.ticker.upper()
        # Try to parse value as number
        try:
            val = float(req.value)
        except ValueError:
            val = req.value
        loader.save_missing_field(ticker, req.field_name, val, req.source)
        # Recompute score with new data
        prices       = loader.get_price_data(ticker)
        fundamentals = loader.get_fundamentals(ticker)
        scores       = scorer.compute_scores(prices, fundamentals)
        _score_cache[ticker] = scores
        return {"success": True, "new_scores": _clean_dict(scores)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════
# GOLD MODULE — routes added below, zero impact on stock routes above
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
                "close":  round(_clean(row["close"])or 0, 2),
                "volume": round(_clean(row.get("volume", 0)) or 0, 2),
                "ema9":   round(_clean(row.get("ema9"))  or 0, 2),
                "ema21":  round(_clean(row.get("ema21")) or 0, 2),
                "ema50":  round(_clean(row.get("ema50")) or 0, 2),
                "ema200": round(_clean(row.get("ema200"))or 0, 2),
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
        df_h4  = fetch_ohlcv(interval="4h",   outputsize=500)
        df_h1  = fetch_ohlcv(interval="1h",   outputsize=300)
        df_m30 = fetch_ohlcv(interval="30min",outputsize=200)
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
        result = run_backtest(
            df,
            start_date=req.start_date,
            end_date=req.end_date,
            atr_sl_mult=req.atr_sl_mult,
            atr_tp_mult=req.atr_tp_mult,
            min_score=req.min_score,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/gold/demo/trades")
def get_demo_trades():
    try:
        return {
            "trades":      demo_manager.get_trades(),
            "performance": demo_manager.get_performance(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/gold/demo/open")
def open_demo_trade(req: DemoTradeRequest):
    try:
        trade = demo_manager.open_trade(
            direction=req.direction, entry=req.entry,
            sl=req.sl, tp1=req.tp1, tp2=req.tp2,
            score=req.score, lot_size=req.lot_size,
        )
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
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
