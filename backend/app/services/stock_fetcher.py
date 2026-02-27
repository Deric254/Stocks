import yfinance as yf
from app.models.db_models import get_connection
from app.services.nyoro_score import compute_nyoro_score
from datetime import date

def fetch_and_update_stock(ticker, name, market="NSE", sector="utilities"):
    """
    Fetch stock price and update SQLite
    """
    stock_data = yf.Ticker(ticker)
    info = stock_data.info

    price = info.get("regularMarketPrice", 0)
    pe_ratio = info.get("trailingPE", 0)
    dividend_yield = info.get("dividendYield", 0) or 0
    avg_52_week = info.get("fiftyTwoWeekAverage", price)
    # 3-month drop estimation
    hist = stock_data.history(period="3mo")
    if not hist.empty:
        price_drop_3m = max(0, (hist['Close'].max() - price) / hist['Close'].max())
    else:
        price_drop_3m = 0

    stock_dict = {
        "ticker": ticker,
        "name": name,
        "market": market,
        "price": price,
        "sector": sector,
        "pe_ratio": pe_ratio,
        "dividend_yield": dividend_yield,
        "avg_52_week": avg_52_week,
        "price_drop_3m": price_drop_3m
    }
    stock_dict["nyoro_score"] = compute_nyoro_score(stock_dict)

    # Save to SQLite
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO stocks 
        (ticker, name, market, price, sector, pe_ratio, dividend_yield, nyoro_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ticker, name, market, price, sector, pe_ratio, dividend_yield, stock_dict["nyoro_score"]
    ))
    # Save price history
    c.execute("""
        INSERT INTO price_history (ticker, date, price)
        VALUES (?, ?, ?)
    """, (ticker, date.today(), price))
    conn.commit()
    conn.close()

    return stock_dict