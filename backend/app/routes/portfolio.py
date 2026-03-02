from fastapi import APIRouter
from datetime import date
from app.models.db_models import get_connection

router = APIRouter()


@router.post("/buy")
def buy_stock(ticker: str, quantity: float):
    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT price FROM stocks WHERE ticker = ?", (ticker,))
    stock = c.fetchone()

    if not stock:
        conn.close()
        return {"error": "Stock not found"}

    price = stock["price"]

    c.execute("""
        INSERT INTO portfolio (ticker, quantity, buy_price, date_bought)
        VALUES (?, ?, ?, ?)
    """, (ticker, quantity, price, date.today()))

    conn.commit()
    conn.close()

    return {"message": "Stock purchased", "ticker": ticker, "quantity": quantity, "price": price}


@router.post("/sell")
def sell_stock(portfolio_id: int):
    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT ticker FROM portfolio WHERE id = ? AND sell_price IS NULL", (portfolio_id,))
    record = c.fetchone()

    if not record:
        conn.close()
        return {"error": "Active position not found"}

    ticker = record["ticker"]

    c.execute("SELECT price FROM stocks WHERE ticker = ?", (ticker,))
    stock = c.fetchone()
    current_price = stock["price"]

    c.execute("""
        UPDATE portfolio
        SET sell_price = ?, date_sold = ?
        WHERE id = ?
    """, (current_price, date.today(), portfolio_id))

    conn.commit()
    conn.close()

    return {"message": "Stock sold", "portfolio_id": portfolio_id, "sell_price": current_price}


@router.get("/")
def view_portfolio():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM portfolio")
    rows = c.fetchall()
    conn.close()

    return [dict(row) for row in rows]