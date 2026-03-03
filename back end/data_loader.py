"""
data_loader.py — Yahoo Finance fetcher with CSV caching.
All prices and fundamentals are stored locally to minimise API calls.
"""

import os
import json
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

PRICES_CSV     = DATA_DIR / "prices_history.csv"
FUNDAMENTALS_CSV = DATA_DIR / "fundamentals.csv"
CONFIG_JSON    = DATA_DIR / "config.json"

# How old cached data can be before we re-fetch (hours)
PRICE_TTL_HOURS = 4
FUND_TTL_HOURS  = 24


def _load_config() -> dict:
    if CONFIG_JSON.exists():
        with open(CONFIG_JSON) as f:
            return json.load(f)
    default = {
        "scoring_weights": {"daily": 0.4, "monthly": 0.3, "long_term": 0.3},
        "api": {"yahoo_source": "yfinance"},
        "ui": {"default_currency": "KES"},
    }
    with open(CONFIG_JSON, "w") as f:
        json.dump(default, f, indent=2)
    return default


class DataLoader:
    def __init__(self):
        self.config = _load_config()

    # ------------------------------------------------------------------ #
    #  Price data                                                          #
    # ------------------------------------------------------------------ #

    def get_price_data(self, ticker: str, period: str = "2y") -> pd.DataFrame:
        """Return OHLCV dataframe for ticker, using CSV cache."""
        cached = self._read_price_cache(ticker)
        if cached is not None:
            return cached

        df = self._fetch_prices_yfinance(ticker, period)
        if not df.empty:
            self._write_price_cache(ticker, df)
        return df

    def _fetch_prices_yfinance(self, ticker: str, period: str) -> pd.DataFrame:
        try:
            obj = yf.Ticker(ticker)
            df  = obj.history(period=period)
            if df.empty:
                return pd.DataFrame()
            df.columns = [c.lower() for c in df.columns]
            df = df[["open", "high", "low", "close", "volume"]]
            df.index = pd.to_datetime(df.index).tz_localize(None)
            return df
        except Exception as e:
            print(f"[DataLoader] yfinance price fetch failed for {ticker}: {e}")
            return pd.DataFrame()

    def _read_price_cache(self, ticker: str) -> pd.DataFrame | None:
        if not PRICES_CSV.exists():
            return None
        try:
            df = pd.read_csv(PRICES_CSV, parse_dates=["date"])
            sub = df[df["ticker"] == ticker].copy()
            if sub.empty:
                return None
            sub = sub.set_index("date").sort_index()
            # Check freshness — last row date
            last_date = sub.index[-1]
            age_hours = (datetime.now() - last_date).total_seconds() / 3600
            if age_hours > PRICE_TTL_HOURS:
                return None          # stale → re-fetch
            sub = sub.drop(columns=["ticker"], errors="ignore")
            return sub
        except Exception:
            return None

    def _write_price_cache(self, ticker: str, df: pd.DataFrame):
        try:
            new = df.copy()
            new["ticker"] = ticker
            new = new.reset_index().rename(columns={"index": "date", "Date": "date"})
            new["date"] = pd.to_datetime(new["date"]).dt.strftime("%Y-%m-%d")

            if PRICES_CSV.exists():
                existing = pd.read_csv(PRICES_CSV)
                existing = existing[existing["ticker"] != ticker]
                combined = pd.concat([existing, new], ignore_index=True)
            else:
                combined = new

            combined.to_csv(PRICES_CSV, index=False)
        except Exception as e:
            print(f"[DataLoader] price cache write failed: {e}")

    # ------------------------------------------------------------------ #
    #  Fundamentals                                                        #
    # ------------------------------------------------------------------ #

    def get_fundamentals(self, ticker: str) -> dict:
        cached = self._read_fund_cache(ticker)
        if cached:
            return cached

        data = self._fetch_fundamentals_yfinance(ticker)
        if data:
            self._write_fund_cache(ticker, data)
        return data

    def _fetch_fundamentals_yfinance(self, ticker: str) -> dict:
        try:
            obj  = yf.Ticker(ticker)
            info = obj.info or {}

            def _safe(key, default=None):
                val = info.get(key, default)
                return val if val is not None else default

            # Compute derived fundamentals
            price = _safe("currentPrice") or _safe("regularMarketPrice", 0)
            eps   = _safe("trailingEps")
            bvps  = _safe("bookValue")
            pe    = round(price / eps, 2)  if eps  and eps  > 0 else None
            pb    = round(price / bvps, 2) if bvps and bvps > 0 else None
            div_yield = _safe("dividendYield")

            return {
                "ticker":         ticker,
                "eps":            eps,
                "bvps":           bvps,
                "revenue":        _safe("totalRevenue"),
                "debt":           _safe("totalDebt"),
                "dividends":      _safe("dividendRate"),
                "roe":            _safe("returnOnEquity"),
                "margin":         _safe("profitMargins"),
                "pe":             pe,
                "pb":             pb,
                "dividend_yield": div_yield,
                "last_update":    datetime.now().strftime("%Y-%m-%d"),
            }
        except Exception as e:
            print(f"[DataLoader] fundamentals fetch failed for {ticker}: {e}")
            return {}

    def _read_fund_cache(self, ticker: str) -> dict | None:
        if not FUNDAMENTALS_CSV.exists():
            return None
        try:
            df = pd.read_csv(FUNDAMENTALS_CSV)
            row = df[df["ticker"] == ticker]
            if row.empty:
                return None
            r = row.iloc[0]
            last = datetime.strptime(str(r.get("last_update", "2000-01-01")), "%Y-%m-%d")
            age  = (datetime.now() - last).total_seconds() / 3600
            if age > FUND_TTL_HOURS:
                return None
            return r.to_dict()
        except Exception:
            return None

    def _write_fund_cache(self, ticker: str, data: dict):
        try:
            row = pd.DataFrame([data])
            if FUNDAMENTALS_CSV.exists():
                existing = pd.read_csv(FUNDAMENTALS_CSV)
                existing = existing[existing["ticker"] != ticker]
                combined = pd.concat([existing, row], ignore_index=True)
            else:
                combined = row
            combined.to_csv(FUNDAMENTALS_CSV, index=False)
        except Exception as e:
            print(f"[DataLoader] fundamentals cache write failed: {e}")
