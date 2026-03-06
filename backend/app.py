"""
Stock Intel API — FastAPI backend
Run with:  python app.py
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import math

from services.data_loader import DataLoader
from services.scoring import ScoringEngine
from services.portfolio import PortfolioManager
from services.analytics import AnalyticsEngine

app = FastAPI(title="Stock Intel API", version="2.0.0")

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

# NSE Tickers — Yahoo Finance uses .NRO suffix for Nairobi Stock Exchange
NSE_TICKERS = [
    {"ticker": "EQTY.NRO", "name": "Equity Group Holdings",    "sector": "Banking"},
    {"ticker": "KCB.NRO",  "name": "KCB Group",                "sector": "Banking"},
    {"ticker": "SCOM.NRO", "name": "Safaricom PLC",            "sector": "Telecom"},
    {"ticker": "EABL.NRO", "name": "East African Breweries",   "sector": "Consumer"},
    {"ticker": "COOP.NRO", "name": "Co-operative Bank",        "sector": "Banking"},
    {"ticker": "ABSA.NRO", "name": "ABSA Bank Kenya",          "sector": "Banking"},
    {"ticker": "BRIT.NRO", "name": "Britam Holdings",          "sector": "Insurance"},
    {"ticker": "JUB.NRO",  "name": "Jubilee Holdings",         "sector": "Insurance"},
    {"ticker": "NCBA.NRO", "name": "NCBA Group",               "sector": "Banking"},
    {"ticker": "DTK.NRO",  "name": "Diamond Trust Bank",       "sector": "Banking"},
    {"ticker": "SCBK.NRO", "name": "Standard Chartered Kenya", "sector": "Banking"},
    {"ticker": "BAT.NRO",  "name": "BAT Kenya",                "sector": "Consumer"},
    {"ticker": "TOTL.NRO", "name": "TotalEnergies Kenya",      "sector": "Energy"},
]

_score_cache: dict = {}   # ticker → scores, populated by /api/stocks


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
    quantity: int
    price: float
    date: str


@app.get("/")
def root():
    return {"message": "Stock Intel API", "status": "running"}


@app.get("/api/tickers")
def get_tickers():
    return {"tickers": NSE_TICKERS}


@app.get("/api/stocks")
def get_stocks(timing: str = "best_pick"):
    global _score_cache
    results = []
    for meta in NSE_TICKERS:
        ticker = meta["ticker"]
        try:
            prices       = loader.get_price_data(ticker)
            fundamentals = loader.get_fundamentals(ticker)
            scores       = scorer.compute_scores(prices, fundamentals)
            _score_cache[ticker] = scores
            current_price = float(prices["close"].iloc[-1]) if not prices.empty else 0
            sparkline = [_clean(p) or 0 for p in prices["close"].tail(10).tolist()] if not prices.empty else []
            results.append({
                "ticker":  ticker,
                "name":    meta["name"],
                "sector":  meta["sector"],
                "scores":  _clean_dict(scores),
                "metrics": {
                    "pe":             _clean(fundamentals.get("pe")),
                    "pb":             _clean(fundamentals.get("pb")),
                    "dividend_yield": _clean(fundamentals.get("dividend_yield")),
                    "price":          round(current_price, 2),
                },
                "sparkline": [round(p, 2) for p in sparkline],
            })
        except Exception as e:
            print(f"[stocks] skip {ticker}: {e}")
            continue
    sort_key = timing if timing in ("daily", "monthly", "long_term", "best_pick") else "best_pick"
    results.sort(key=lambda x: x["scores"].get(sort_key) or 0, reverse=True)
    return {"stocks": results}


@app.get("/api/stock/{ticker_raw:path}")
def get_stock(ticker_raw: str):
    try:
        ticker = ticker_raw.upper()
        if "." not in ticker:
            ticker = ticker + ".NRO"
        prices       = loader.get_price_data(ticker)
        fundamentals = loader.get_fundamentals(ticker)
        scores       = scorer.compute_scores(prices, fundamentals)
        position     = portfolio.get_position(ticker)
        price_history = []
        if not prices.empty:
            for dt, row in prices.tail(365).iterrows():
                try:
                    price_history.append({
                        "date":   str(dt.date() if hasattr(dt, "date") else dt),
                        "open":   round(_clean(row["open"]) or 0, 2),
                        "high":   round(_clean(row["high"]) or 0, 2),
                        "low":    round(_clean(row["low"])  or 0, 2),
                        "close":  round(_clean(row["close"])or 0, 2),
                        "volume": int(row["volume"]) if not math.isnan(float(row["volume"])) else 0,
                    })
                except Exception:
                    continue
        meta = next((s for s in NSE_TICKERS if s["ticker"] == ticker),
                    {"name": ticker, "sector": "Unknown"})
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
            },
            "my_position": position,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _enrich(summary: dict) -> dict:
    total_invested = 0.0
    current_value  = 0.0
    realized_total = 0.0
    enriched = []
    for h in summary.get("holdings", []):
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
            bp = _clean(_score_cache[ticker].get("best_pick"))
            bp_score = round(bp) if bp is not None else None
        unr = round((cp - avg_cost) * qty, 2)
        total_invested += avg_cost * qty
        current_value  += cp * qty
        realized_total += h.get("realized_pl", 0)
        enriched.append({
            "ticker":          ticker,
            "quantity":        qty,
            "avg_cost":        round(avg_cost, 2),
            "current_price":   round(cp, 2),
            "unrealized_pl":   unr,
            "realized_pl":     round(h.get("realized_pl", 0), 2),
            "holding_days":    h.get("holding_days", 0),
            "best_pick_score": bp_score,
        })
    unr_total  = current_value - total_invested
    return_pct = unr_total / total_invested if total_invested > 0 else 0.0
    return {
        "summary": {
            "total_invested": round(total_invested, 2),
            "current_value":  round(current_value, 2),
            "unrealized_pl":  round(unr_total, 2),
            "realized_pl":    round(realized_total, 2),
            "return_pct":     round(return_pct, 4),
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
            ticker = ticker + ".NRO"
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


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
