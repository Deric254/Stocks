"""
analytics.py — Equity curve, monthly performance, best/worst picks,
               holding stats, yield projections.
"""

import math
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict


class AnalyticsEngine:

    def get_analytics(self, portfolio_mgr, loader, scorer, stock_meta_list: list) -> dict:
        """
        Full analytics payload for the /api/analytics endpoint.
        """
        trades_df = pd.DataFrame(portfolio_mgr.get_all_trades())

        equity_curve      = self._build_equity_curve(trades_df, loader)
        monthly_perf      = self._monthly_performance(equity_curve)
        best_picks, worst = self._pick_performance(trades_df, loader)
        avg_holding       = self._avg_holding_days(trades_df)
        projections       = self._compounding_projections(portfolio_mgr, loader)

        return {
            "equity_curve":         equity_curve,
            "monthly_performance":  monthly_perf,
            "best_picks":           best_picks,
            "worst_picks":          worst,
            "avg_holding_days":     avg_holding,
            "projections":          projections,
        }

    # ──────────────────────────────────────────────────────────────────────
    #  Equity curve
    # ──────────────────────────────────────────────────────────────────────

    def _build_equity_curve(self, trades_df: pd.DataFrame,
                            loader) -> list[dict]:
        """
        Build daily portfolio value from first trade date to today.
        For each day: sum(qty_held * close_price) for all open positions.
        """
        if trades_df.empty:
            return []

        trades_df = trades_df.copy()
        trades_df["date"] = pd.to_datetime(trades_df["date"])
        trades_df = trades_df.sort_values("date")

        start = trades_df["date"].min()
        end   = datetime.now()
        date_range = pd.date_range(start=start, end=end, freq="B")  # business days

        tickers = trades_df["ticker"].unique()

        # Pre-load price series for all tickers
        price_series = {}
        for t in tickers:
            try:
                df = loader.get_price_data(t)
                if not df.empty:
                    df.index = pd.to_datetime(df.index).normalize()
                    price_series[t] = df["close"]
            except Exception:
                pass

        curve = []
        for day in date_range:
            day = day.normalize()
            # Compute holdings as of this day
            daily_trades = trades_df[trades_df["date"] <= day]
            positions    = self._positions_at(daily_trades)

            portfolio_value = 0.0
            for ticker, pos in positions.items():
                if ticker in price_series:
                    series = price_series[ticker]
                    # Get closest available price on or before this day
                    avail = series[series.index <= day]
                    price = float(avail.iloc[-1]) if not avail.empty else pos["avg_cost"]
                else:
                    price = pos["avg_cost"]
                portfolio_value += pos["quantity"] * price

            if portfolio_value > 0:
                curve.append({
                    "date":  day.strftime("%Y-%m-%d"),
                    "value": round(portfolio_value, 2),
                })

        return curve

    def _positions_at(self, trades_df: pd.DataFrame) -> dict:
        """Simplified position snapshot (no FIFO needed here — just net qty)."""
        positions = defaultdict(lambda: {"quantity": 0, "total_cost": 0.0})

        for _, row in trades_df.iterrows():
            t     = row["ticker"]
            qty   = int(row["quantity"])
            price = float(row["price"])
            if row["trade_type"] == "BUY":
                positions[t]["quantity"]   += qty
                positions[t]["total_cost"] += qty * price
            elif row["trade_type"] == "SELL":
                positions[t]["quantity"] = max(0, positions[t]["quantity"] - qty)

        result = {}
        for t, p in positions.items():
            if p["quantity"] > 0:
                avg = p["total_cost"] / p["quantity"] if p["quantity"] > 0 else 0
                result[t] = {"quantity": p["quantity"], "avg_cost": avg}
        return result

    # ──────────────────────────────────────────────────────────────────────
    #  Monthly performance
    # ──────────────────────────────────────────────────────────────────────

    def _monthly_performance(self, equity_curve: list[dict]) -> list[dict]:
        if not equity_curve:
            return []

        df = pd.DataFrame(equity_curve)
        df["date"]  = pd.to_datetime(df["date"])
        df["month"] = df["date"].dt.to_period("M")

        monthly = df.groupby("month")["value"].agg(["first", "last"]).reset_index()
        result  = []
        for _, row in monthly.iterrows():
            if row["first"] and row["first"] > 0:
                ret = (row["last"] - row["first"]) / row["first"]
                result.append({
                    "month":      str(row["month"]),
                    "return_pct": round(ret, 4),
                    "start_value": round(row["first"], 2),
                    "end_value":   round(row["last"], 2),
                })
        return result

    # ──────────────────────────────────────────────────────────────────────
    #  Best / worst picks
    # ──────────────────────────────────────────────────────────────────────

    def _pick_performance(self, trades_df: pd.DataFrame,
                          loader) -> tuple[list, list]:
        if trades_df.empty:
            return [], []

        tickers = trades_df["ticker"].unique()
        perf    = []

        for ticker in tickers:
            try:
                t_df = trades_df[trades_df["ticker"] == ticker]
                buys = t_df[t_df["trade_type"] == "BUY"]
                if buys.empty:
                    continue

                avg_buy = float((buys["quantity"].astype(float) *
                                 buys["price"].astype(float)).sum() /
                                buys["quantity"].astype(float).sum())

                prices = loader.get_price_data(ticker)
                current = float(prices["close"].iloc[-1]) if not prices.empty else avg_buy

                ret = (current - avg_buy) / avg_buy if avg_buy > 0 else 0.0
                perf.append({"ticker": ticker, "avg_cost": round(avg_buy, 2),
                             "current_price": round(current, 2),
                             "return_pct": round(ret, 4)})
            except Exception:
                continue

        perf.sort(key=lambda x: x["return_pct"], reverse=True)
        best  = perf[:5]
        worst = sorted(perf, key=lambda x: x["return_pct"])[:5]
        return best, worst

    # ──────────────────────────────────────────────────────────────────────
    #  Average holding days
    # ──────────────────────────────────────────────────────────────────────

    def _avg_holding_days(self, trades_df: pd.DataFrame) -> float:
        if trades_df.empty:
            return 0.0

        trades_df = trades_df.copy()
        trades_df["date"] = pd.to_datetime(trades_df["date"])
        buys = trades_df[trades_df["trade_type"] == "BUY"]
        if buys.empty:
            return 0.0

        holding_days = (datetime.now() - buys["date"]).dt.days
        return round(float(holding_days.mean()), 1)

    # ──────────────────────────────────────────────────────────────────────
    #  Compounding / yield projections
    # ──────────────────────────────────────────────────────────────────────

    def _compounding_projections(self, portfolio_mgr, loader) -> list[dict]:
        """
        Project portfolio value assuming current return rate continues,
        compounded annually for 1, 3, 5, 10 years.
        """
        try:
            summary = portfolio_mgr.get_summary(loader)
            current_value   = summary["summary"]["current_value"]
            total_invested  = summary["summary"]["total_invested"]

            if total_invested <= 0 or current_value <= 0:
                return []

            # Annualise return — use unrealized return as proxy
            return_pct = summary["summary"]["return_pct"]
            # Clamp to realistic range
            annual_rate = max(-0.5, min(return_pct, 1.0))

            projections = []
            for years in [1, 3, 5, 10]:
                projected = current_value * math.pow(1 + annual_rate, years)
                projections.append({
                    "years":           years,
                    "projected_value": round(projected, 2),
                    "assumed_rate":    round(annual_rate, 4),
                })
            return projections
        except Exception:
            return []
