import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "database" / "dericbi.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # Stocks table
    c.execute("""
    CREATE TABLE IF NOT EXISTS stocks (
        ticker TEXT PRIMARY KEY,
        name TEXT,
        market TEXT,
        price REAL,
        sector TEXT,
        pe_ratio REAL,
        dividend_yield REAL,
        nyoro_score INTEGER
    )
    """)
    # Watchlist table
    c.execute("""
    CREATE TABLE IF NOT EXISTS watchlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT,
        date_added DATE
    )
    """)
    # Portfolio table
    c.execute("""
    CREATE TABLE IF NOT EXISTS portfolio (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT,
        quantity REAL,
        buy_price REAL,
        date_bought DATE,
        sell_price REAL,
        date_sold DATE
    )
    """)
    # Price history table
    c.execute("""
    CREATE TABLE IF NOT EXISTS price_history (
        ticker TEXT,
        date DATE,
        price REAL
    )
    """)
    conn.commit()
    conn.close()