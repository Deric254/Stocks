"""
portfolio.py — Trade storage and position calculation with DIVIDEND support.
"""

import uuid
import pandas as pd
from datetime import datetime

from services.paths import DATA_DIR
TRADES_CSV = DATA_DIR / "portfolio_trades.csv"

COLUMNS = ["trade_id", "ticker", "trade_type", "quantity", "price", "date"]


def _load_trades() -> pd.DataFrame:
    if TRADES_CSV.exists():
        try:
            df = pd.read_csv(TRADES_CSV)
            # ensure all needed columns exist
            for col in COLUMNS:
                if col not in df.columns:
                    df[col] = None
            return df[COLUMNS]
        except Exception:
            pass
    return pd.DataFrame(columns=COLUMNS)


def _save_trades(df: pd.DataFrame):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(TRADES_CSV, index=False)


class PortfolioManager:

    def add_trade(self, ticker: str, trade_type: str, quantity, price, date: str):
        if trade_type not in ("BUY", "SELL", "DIVIDEND"):
            raise ValueError("trade_type must be BUY, SELL, or DIVIDEND")
        df = _load_trades()
        new_row = pd.DataFrame([{
            "trade_id":   str(uuid.uuid4()),
            "ticker":     ticker.upper(),
            "trade_type": trade_type,
            "quantity":   float(quantity) if quantity else 0,
            "price":      float(price) if price else 0,
            "date":       date,
        }])
        df = pd.concat([df, new_row], ignore_index=True)
        _save_trades(df)

    def get_all_trades(self) -> list:
        return _load_trades().to_dict(orient="records")

    def _compute_positions(self) -> dict:
        df = _load_trades()
        if df.empty:
            return {}

        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")

        positions = {}

        for _, row in df.iterrows():
            ticker = row["ticker"]
            qty    = float(row["quantity"] or 0)
            price  = float(row["price"] or 0)

            if ticker not in positions:
                positions[ticker] = {
                    "lots": [], "realized_pl": 0.0, "dividends_received": 0.0
                }

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

            elif row["trade_type"] == "DIVIDEND":
                # price field = dividend amount per share; quantity = shares held
                positions[ticker]["dividends_received"] += qty * price

        result = {}
        for ticker, pos in positions.items():
            total_qty = sum(l[0] for l in pos["lots"])
            if total_qty <= 0:
                continue
            total_cost = sum(l[0] * l[1] for l in pos["lots"])
            avg_cost   = total_cost / total_qty

            t_rows = df[(df["ticker"] == ticker) & (df["trade_type"] == "BUY")]
            first_buy = t_rows["date"].min() if not t_rows.empty else datetime.now()
            holding_days = (datetime.now() - first_buy).days

            result[ticker] = {
                "quantity":             total_qty,
                "avg_cost":             round(avg_cost, 4),
                "total_invested":       round(total_cost, 2),
                "realized_pl":          round(pos["realized_pl"], 2),
                "dividends_received":   round(pos["dividends_received"], 2),
                "holding_days":         holding_days,
            }

        return result

    def get_position(self, ticker: str):
        return self._compute_positions().get(ticker.upper())

    def get_summary(self, loader) -> dict:
        positions = self._compute_positions()

        total_invested    = 0.0
        current_value     = 0.0
        realized_pl_total = 0.0
        dividends_total   = 0.0
        holdings          = []

        for ticker, pos in positions.items():
            try:
                prices = loader.get_price_data(ticker)
                current_price = float(prices["close"].iloc[-1]) if not prices.empty else pos["avg_cost"]
            except Exception:
                current_price = pos["avg_cost"]

            unrealized_pl = (current_price - pos["avg_cost"]) * pos["quantity"]
            total_invested    += pos["total_invested"]
            current_value     += current_price * pos["quantity"]
            realized_pl_total += pos["realized_pl"]
            dividends_total   += pos["dividends_received"]

            holdings.append({
                "ticker":              ticker,
                "quantity":            pos["quantity"],
                "avg_cost":            round(pos["avg_cost"], 2),
                "current_price":       round(current_price, 2),
                "unrealized_pl":       round(unrealized_pl, 2),
                "realized_pl":         round(pos["realized_pl"], 2),
                "dividends_received":  round(pos["dividends_received"], 2),
                "holding_days":        pos["holding_days"],
                "best_pick_score":     None,
            })

        unrealized_total = current_value - total_invested
        return_pct = (unrealized_total / total_invested) if total_invested > 0 else 0.0

        # Annualised return (approx) — weighted avg holding period
        if holdings:
            avg_days = sum(h["holding_days"] for h in holdings) / len(holdings)
            years    = max(avg_days / 365, 0.001)
            ann_return = ((1 + return_pct) ** (1 / years)) - 1 if return_pct > -1 else -1
        else:
            ann_return = 0.0

        return {
            "summary": {
                "total_invested":    round(total_invested, 2),
                "current_value":     round(current_value, 2),
                "unrealized_pl":     round(unrealized_total, 2),
                "realized_pl":       round(realized_pl_total, 2),
                "return_pct":        round(return_pct, 4),
                "annualized_return": round(ann_return, 4),
                "dividends_ytd":     round(dividends_total, 2),
            },
            "holdings": holdings,
        }
