"""
Stock Intel API — FastAPI backend (full spec implementation)
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
import math

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
    global _score_cache
    results = []
    tickers = NSE_TICKERS
    if sector:
        tickers = [t for t in NSE_TICKERS if t["sector"].lower() == sector.lower()]

    for meta in tickers:
        ticker = meta["ticker"]
        try:
            prices       = loader.get_price_data(ticker)
            fundamentals = loader.get_fundamentals(ticker)
            scores       = scorer.compute_scores(prices, fundamentals)
            _score_cache[ticker] = scores

            current_price = float(prices["close"].iloc[-1]) if not prices.empty else 0
            sparkline = [_clean(p) or 0 for p in prices["close"].tail(10).tolist()] if not prices.empty else []

            # Asset coverage for screener column
            total_assets = _clean(fundamentals.get("total_assets"))
            market_cap   = _clean(fundamentals.get("market_cap"))
            asset_cov    = round(total_assets / market_cap, 2) if (total_assets and market_cap and market_cap > 0) else None

            results.append({
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
                },
                "sparkline": [round(p, 2) for p in sparkline],
            })
        except Exception as e:
            print(f"[stocks] skip {ticker}: {e}")
            continue

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

    return {"stocks": results}


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


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
