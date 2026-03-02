from fastapi import APIRouter
from app.models.db_models import get_connection
from app.services.stock_fetcher import fetch_and_update_stock

router = APIRouter()

# Sample starter stocks (can expand later)
DEFAULT_STOCKS = [
    {"ticker": "KPLC.NR", "name": "Kenya Power", "market": "NSE", "sector": "utilities"},
    {"ticker": "KGEN.NR", "name": "KenGen", "market": "NSE", "sector": "utilities"},
    {"ticker": "COOP.NR", "name": "Co-operative Bank", "market": "NSE", "sector": "financial"},
    {"ticker": "AAPL", "name": "Apple Inc", "market": "NASDAQ", "sector": "technology"},
]


@router.get("/refresh")
def refresh_stocks():
    """
    Fetch live prices and update database
    """
    updated = []
    for stock in DEFAULT_STOCKS:
        result = fetch_and_update_stock(
            ticker=stock["ticker"],
            name=stock["name"],
            market=stock["market"],
            sector=stock["sector"]
        )
        updated.append(result)
    return {"updated": updated}


@router.get("/")
def list_stocks(min_score: int = 0):
    """
    List stocks filtered by Nyoro score
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM stocks WHERE nyoro_score >= ?", (min_score,))
    rows = c.fetchall()
    conn.close()

    return [dict(row) for row in rows]