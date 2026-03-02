from fastapi import APIRouter
from app.models.db_models import get_connection

router = APIRouter()


@router.get("/summary")
def portfolio_summary():
    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT * FROM portfolio")
    positions = c.fetchall()

    total_invested = 0
    current_value = 0
    realized_profit = 0

    for pos in positions:
        quantity = pos["quantity"]
        buy_price = pos["buy_price"]
        total_invested += quantity * buy_price

        if pos["sell_price"]:
            realized_profit += quantity * (pos["sell_price"] - buy_price)
        else:
            c.execute("SELECT price FROM stocks WHERE ticker = ?", (pos["ticker"],))
            current_price = c.fetchone()["price"]
            current_value += quantity * current_price

    conn.close()

    unrealized_profit = current_value - total_invested

    return {
        "total_invested": total_invested,
        "current_value": current_value,
        "realized_profit": realized_profit,
        "unrealized_profit": unrealized_profit
    }


@router.get("/positions")
def position_performance():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        SELECT p.*, s.price as current_price
        FROM portfolio p
        LEFT JOIN stocks s ON p.ticker = s.ticker
    """)

    rows = c.fetchall()
    conn.close()

    performance = []

    for row in rows:
        quantity = row["quantity"]
        buy_price = row["buy_price"]
        current_price = row["current_price"]
        pnl = (current_price - buy_price) * quantity

        performance.append({
            "ticker": row["ticker"],
            "quantity": quantity,
            "buy_price": buy_price,
            "current_price": current_price,
            "pnl": pnl
        })

    return performance