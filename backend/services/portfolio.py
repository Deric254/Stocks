"""
portfolio.py — Trade storage and position calculation.

All trades are written to portfolio_trades.csv.
Positions are recomputed from scratch each time (no state).
"""

import uuid
import pandas as pd
from datetime import datetime
from pathlib import Path

DATA_DIR   = Path(__file__).parent.parent / "data"
TRADES_CSV = DATA_DIR / "portfolio_trades.csv"

COLUMNS = ["trade_id", "ticker", "trade_type", "quantity", "price", "date"]


def _load_trades() -> pd.DataFrame:
    if TRADES_CSV.exists():
        try:
            df = pd.read_csv(TRADES_CSV)
            return df[COLUMNS] if set(COLUMNS).issubset(df.columns) else pd.DataFrame(columns=COLUMNS)
        except Exception:
            pass
    return pd.DataFrame(columns=COLUMNS)


def _save_trades(df: pd.DataFrame):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(TRADES_CSV, index=False)


class PortfolioManager:

    # ──────────────────────────────────────────────────────────────────────
    #  Trade I/O
    # ──────────────────────────────────────────────────────────────────────

    def add_trade(self, ticker: str, trade_type: str, quantity: int,
                  price: float, date: str):
        """Append a trade row to the CSV."""
        if trade_type not in ("BUY", "SELL"):
            raise ValueError("trade_type must be BUY or SELL")

        df = _load_trades()
        new_row = pd.DataFrame([{
            "trade_id":   str(uuid.uuid4()),
            "ticker":     ticker.upper(),
            "trade_type": trade_type,
            "quantity":   int(quantity),
            "price":      float(price),
            "date":       date,
        }])
        df = pd.concat([df, new_row], ignore_index=True)
        _save_trades(df)

    def get_all_trades(self) -> list[dict]:
        df = _load_trades()
        return df.to_dict(orient="records")

    # ──────────────────────────────────────────────────────────────────────
    #  Position computation
    # ──────────────────────────────────────────────────────────────────────

    def _compute_positions(self) -> dict:
        """
        Returns dict of ticker → position dict with:
          quantity, avg_cost, total_invested, realized_pl
        Uses FIFO for realised P/L on sells.
        """
        df = _load_trades()
        if df.empty:
            return {}

        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")

        positions = {}  # ticker → {lots: [(qty, price)], realized_pl}

        for _, row in df.iterrows():
            ticker = row["ticker"]
            qty    = int(row["quantity"])
            price  = float(row["price"])

            if ticker not in positions:
                positions[ticker] = {"lots": [], "realized_pl": 0.0}

            if row["trade_type"] == "BUY":
                positions[ticker]["lots"].append([qty, price])

            elif row["trade_type"] == "SELL":
                remaining = qty
                while remaining > 0 and positions[ticker]["lots"]:
                    lot_qty, lot_price = positions[ticker]["lots"][0]
                    sold = min(remaining, lot_qty)
                    positions[ticker]["realized_pl"] += sold * (price - lot_price)
                    if sold == lot_qty:
                        positions[ticker]["lots"].pop(0)
                    else:
                        positions[ticker]["lots"][0][0] -= sold
                    remaining -= sold

        result = {}
        for ticker, pos in positions.items():
            total_qty  = sum(l[0] for l in pos["lots"])
            if total_qty <= 0:
                continue
            total_cost = sum(l[0] * l[1] for l in pos["lots"])
            avg_cost   = total_cost / total_qty

            # Holding days from earliest remaining lot's buy date
            # (approximate: use earliest trade date for this ticker)
            t_rows = df[(df["ticker"] == ticker) & (df["trade_type"] == "BUY")]
            first_buy = t_rows["date"].min() if not t_rows.empty else datetime.now()
            holding_days = (datetime.now() - first_buy).days

            result[ticker] = {
                "quantity":      total_qty,
                "avg_cost":      round(avg_cost, 4),
                "total_invested": round(total_cost, 2),
                "realized_pl":   round(pos["realized_pl"], 2),
                "holding_days":  holding_days,
            }

        return result

    def get_position(self, ticker: str) -> dict | None:
        positions = self._compute_positions()
        return positions.get(ticker.upper())

    # ──────────────────────────────────────────────────────────────────────
    #  Portfolio summary
    # ──────────────────────────────────────────────────────────────────────

    def get_summary(self, loader) -> dict:
        """Build full portfolio summary using live prices."""
        positions = self._compute_positions()

        total_invested   = 0.0
        current_value    = 0.0
        realized_pl_total = 0.0
        holdings         = []

        for ticker, pos in positions.items():
            try:
                prices = loader.get_price_data(ticker)
                current_price = float(prices["close"].iloc[-1]) if not prices.empty else pos["avg_cost"]
            except Exception:
                current_price = pos["avg_cost"]

            unrealized_pl = (current_price - pos["avg_cost"]) * pos["quantity"]
            total_invested   += pos["total_invested"]
            current_value    += current_price * pos["quantity"]
            realized_pl_total += pos["realized_pl"]

            holdings.append({
                "ticker":         ticker,
                "quantity":       pos["quantity"],
                "avg_cost":       round(pos["avg_cost"], 2),
                "current_price":  round(current_price, 2),
                "unrealized_pl":  round(unrealized_pl, 2),
                "realized_pl":    round(pos["realized_pl"], 2),
                "holding_days":   pos["holding_days"],
                "best_pick_score": None,   # filled by caller if needed
            })

        unrealized_total = current_value - total_invested
        return_pct = (unrealized_total / total_invested) if total_invested > 0 else 0.0

        return {
            "summary": {
                "total_invested":  round(total_invested, 2),
                "current_value":   round(current_value, 2),
                "unrealized_pl":   round(unrealized_total, 2),
                "realized_pl":     round(realized_pl_total, 2),
                "return_pct":      round(return_pct, 4),
            },
            "holdings": holdings,
        }
