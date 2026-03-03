from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn

from services.data_loader import DataLoader
from services.scoring import ScoringEngine
from services.portfolio import PortfolioManager
from services.analytics import AnalyticsEngine

app = FastAPI(title="DericBI Stock Intelligence API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

loader = DataLoader()
scorer = ScoringEngine()
portfolio = PortfolioManager()
analytics = AnalyticsEngine()

# Kenyan NSE tickers available via Yahoo Finance
NSE_TICKERS = [
    {"ticker": "EQTY.NR", "name": "Equity Group", "sector": "Banking"},
    {"ticker": "KCB.NR",  "name": "KCB Group",    "sector": "Banking"},
    {"ticker": "SCOM.NR", "name": "Safaricom",     "sector": "Telecom"},
    {"ticker": "EABL.NR", "name": "East African Breweries", "sector": "Consumer"},
    {"ticker": "COOP.NR", "name": "Co-op Bank",   "sector": "Banking"},
    {"ticker": "ABSA.NR", "name": "ABSA Bank Kenya","sector": "Banking"},
    {"ticker": "BAMB.NR", "name": "Bamburi Cement","sector": "Manufacturing"},
    {"ticker": "BRIT.NR", "name": "Britam Holdings","sector": "Insurance"},
    {"ticker": "JUB.NR",  "name": "Jubilee Holdings","sector": "Insurance"},
    {"ticker": "NCBA.NR", "name": "NCBA Group",    "sector": "Banking"},
]


class TradeRequest(BaseModel):
    ticker: str
    trade_type: str  # BUY or SELL
    quantity: int
    price: float
    date: str


@app.get("/")
def root():
    return {"message": "DericBI Stock Intelligence API", "status": "running"}


@app.get("/api/stocks")
def get_stocks(timing: str = "best_pick", category: str = "best_pick"):
    results = []
    for stock_meta in NSE_TICKERS:
        ticker = stock_meta["ticker"]
        try:
            price_data = loader.get_price_data(ticker)
            fundamentals = loader.get_fundamentals(ticker)
            scores = scorer.compute_scores(price_data, fundamentals)
            current_price = price_data["close"].iloc[-1] if not price_data.empty else 0
            sparkline = price_data["close"].tail(10).tolist() if not price_data.empty else []

            results.append({
                "ticker": ticker,
                "name": stock_meta["name"],
                "sector": stock_meta["sector"],
                "scores": scores,
                "metrics": {
                    "pe": fundamentals.get("pe", None),
                    "pb": fundamentals.get("pb", None),
                    "dividend_yield": fundamentals.get("dividend_yield", None),
                    "price": round(current_price, 2),
                },
                "sparkline": [round(p, 2) for p in sparkline],
            })
        except Exception as e:
            print(f"Error loading {ticker}: {e}")
            continue

    # Sort based on timing
    sort_key = {
        "daily": "daily",
        "monthly": "monthly",
        "long_term": "long_term",
        "best_pick": "best_pick",
    }.get(timing, "best_pick")

    results.sort(key=lambda x: x["scores"].get(sort_key, 0), reverse=True)
    return {"stocks": results}


@app.get("/api/stock/{ticker}")
def get_stock(ticker: str):
    try:
        price_data = loader.get_price_data(ticker)
        fundamentals = loader.get_fundamentals(ticker)
        scores = scorer.compute_scores(price_data, fundamentals)
        position = portfolio.get_position(ticker)

        price_history = []
        if not price_data.empty:
            for _, row in price_data.tail(365).iterrows():
                price_history.append({
                    "date": str(row.name.date() if hasattr(row.name, 'date') else row.name),
                    "open": round(float(row["open"]), 2),
                    "high": round(float(row["high"]), 2),
                    "low": round(float(row["low"]), 2),
                    "close": round(float(row["close"]), 2),
                    "volume": int(row["volume"]),
                })

        stock_meta = next((s for s in NSE_TICKERS if s["ticker"] == ticker), {"name": ticker, "sector": "Unknown"})

        return {
            "ticker": ticker,
            "name": stock_meta["name"],
            "sector": stock_meta["sector"],
            "scores": scores,
            "price_history": price_history,
            "fundamentals": {
                "eps": fundamentals.get("eps"),
                "bvps": fundamentals.get("bvps"),
                "revenue": fundamentals.get("revenue"),
                "debt": fundamentals.get("debt"),
                "dividends": fundamentals.get("dividends"),
                "roe": fundamentals.get("roe"),
                "margin": fundamentals.get("margin"),
            },
            "my_position": position,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/portfolio")
def get_portfolio():
    try:
        return portfolio.get_summary(loader)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trades")
def add_trade(trade: TradeRequest):
    try:
        portfolio.add_trade(
            ticker=trade.ticker,
            trade_type=trade.trade_type.upper(),
            quantity=trade.quantity,
            price=trade.price,
            date=trade.date,
        )
        return portfolio.get_summary(loader)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analytics")
def get_analytics():
    try:
        return analytics.get_analytics(portfolio, loader, scorer, NSE_TICKERS)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=7860, reload=True)
