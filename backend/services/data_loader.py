"""
data_loader.py — Yahoo Finance fetcher with CSV caching.
Enriches fundamentals with 5-year history arrays for the 60-point scorer.
"""

import os
import json
import math
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR         = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

PRICES_CSV       = DATA_DIR / "prices_history.csv"
FUNDAMENTALS_CSV = DATA_DIR / "fundamentals.csv"
CONFIG_JSON      = DATA_DIR / "config.json"
WATCHLIST_JSON   = DATA_DIR / "watchlist.json"
MISSING_JSON     = DATA_DIR / "missing_data.json"

PRICE_TTL_HOURS  = 4
FUND_TTL_HOURS   = 24


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


def _safe_float(val, default=None):
    if val is None:
        return default
    try:
        f = float(val)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except Exception:
        return default


class DataLoader:
    def __init__(self):
        self.config = _load_config()

    # ------------------------------------------------------------------ #
    #  Price data                                                          #
    # ------------------------------------------------------------------ #

    def get_price_data(self, ticker: str, period: str = "2y") -> pd.DataFrame:
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

    def _read_price_cache(self, ticker: str):
        if not PRICES_CSV.exists():
            return None
        try:
            df  = pd.read_csv(PRICES_CSV, parse_dates=["date"])
            sub = df[df["ticker"] == ticker].copy()
            if sub.empty:
                return None
            sub = sub.set_index("date").sort_index()
            last_date = sub.index[-1]
            age_hours = (datetime.now() - last_date).total_seconds() / 3600
            if age_hours > PRICE_TTL_HOURS:
                return None
            return sub.drop(columns=["ticker"], errors="ignore")
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
    #  Fundamentals — enriched with 5-year history                        #
    # ------------------------------------------------------------------ #

    def get_fundamentals(self, ticker: str) -> dict:
        cached = self._read_fund_cache(ticker)
        if cached:
            return self._inject_missing_data(ticker, cached)
        data = self._fetch_fundamentals_yfinance(ticker)
        if data:
            self._write_fund_cache(ticker, data)
        return self._inject_missing_data(ticker, data)

    def _fetch_fundamentals_yfinance(self, ticker: str) -> dict:
        try:
            obj  = yf.Ticker(ticker)
            info = obj.info or {}

            price = _safe_float(info.get("currentPrice")) or _safe_float(info.get("regularMarketPrice"), 0)
            eps   = _safe_float(info.get("trailingEps"))
            bvps  = _safe_float(info.get("bookValue"))
            pe    = round(price / eps, 2) if eps and eps > 0 else None
            pb    = round(price / bvps, 2) if bvps and bvps > 0 else None

            # Try to get 5-year income statement history
            net_income_history = []
            revenue_history    = []
            dps_history        = []

            try:
                fin = obj.financials  # annual, columns = dates descending
                if fin is not None and not fin.empty:
                    ni_row  = fin.loc["Net Income"] if "Net Income" in fin.index else None
                    rev_row = fin.loc["Total Revenue"] if "Total Revenue" in fin.index else None
                    if ni_row is not None:
                        net_income_history = [_safe_float(v, 0) for v in reversed(ni_row.values[:5])]
                    if rev_row is not None:
                        revenue_history    = [_safe_float(v, 0) for v in reversed(rev_row.values[:5])]
            except Exception:
                pass

            try:
                div_hist = obj.dividends
                if div_hist is not None and not div_hist.empty:
                    div_hist.index = pd.to_datetime(div_hist.index).tz_localize(None)
                    # DPS by year (last 5 years)
                    div_hist = div_hist.groupby(div_hist.index.year).sum()
                    current_year = datetime.now().year
                    for yr in range(current_year - 4, current_year + 1):
                        dps_history.append(float(div_hist.get(yr, 0)))
            except Exception:
                pass

            # Market cap and total assets for asset safety
            market_cap   = _safe_float(info.get("marketCap"))
            total_assets = _safe_float(info.get("totalAssets"))
            total_debt   = _safe_float(info.get("totalDebt"), 0)

            # Debt-to-equity
            de = _safe_float(info.get("debtToEquity"))
            if de is not None:
                de = de / 100  # yfinance gives it as percentage

            # Interest coverage: not directly in yfinance; use ebitda/interest estimate
            ebitda = _safe_float(info.get("ebitda"))
            interest_exp = None
            try:
                cf = obj.financials
                if cf is not None and "Interest Expense" in cf.index:
                    interest_exp = abs(_safe_float(cf.loc["Interest Expense"].iloc[0], 0))
            except Exception:
                pass
            icr = (ebitda / interest_exp) if (ebitda and interest_exp and interest_exp > 0) else None

            # Total dividends paid (latest year)
            total_dividends = dps_history[-1] * _safe_float(info.get("sharesOutstanding"), 0) if dps_history else 0

            net_income_latest = net_income_history[-1] if net_income_history else _safe_float(info.get("netIncomeToCommon"))

            return {
                "ticker":              ticker,
                "eps":                 eps,
                "bvps":                bvps,
                "revenue":             _safe_float(info.get("totalRevenue")),
                "debt":                total_debt,
                "dividends":           _safe_float(info.get("dividendRate")),
                "roe":                 _safe_float(info.get("returnOnEquity")),
                "margin":              _safe_float(info.get("profitMargins")),
                "pe":                  pe,
                "pb":                  pb,
                "dividend_yield":      _safe_float(info.get("dividendYield")),
                "market_cap":          market_cap,
                "total_assets":        total_assets,
                "debt_to_equity":      de,
                "interest_coverage":   icr,
                "net_income":          net_income_latest,
                "total_dividends":     total_dividends,
                # 5-year history arrays for scoring
                "net_income_history":  net_income_history,
                "revenue_history":     revenue_history,
                "dps_history":         dps_history,
                "last_update":         datetime.now().strftime("%Y-%m-%d"),
            }
        except Exception as e:
            print(f"[DataLoader] fundamentals fetch failed for {ticker}: {e}")
            return {}

    def _read_fund_cache(self, ticker: str):
        if not FUNDAMENTALS_CSV.exists():
            return None
        try:
            df  = pd.read_csv(FUNDAMENTALS_CSV)
            row = df[df["ticker"] == ticker]
            if row.empty:
                return None
            r    = row.iloc[0]
            last = datetime.strptime(str(r.get("last_update", "2000-01-01")), "%Y-%m-%d")
            age  = (datetime.now() - last).total_seconds() / 3600
            if age > FUND_TTL_HOURS:
                return None
            d = r.to_dict()
            # Restore list fields from JSON strings
            for field in ("net_income_history", "revenue_history", "dps_history"):
                v = d.get(field, "[]")
                if isinstance(v, str):
                    try:
                        import json as _json
                        d[field] = _json.loads(v)
                    except Exception:
                        d[field] = []
            return d
        except Exception:
            return None

    def _write_fund_cache(self, ticker: str, data: dict):
        try:
            import json as _json
            row_data = dict(data)
            # Serialise list fields as JSON strings for CSV storage
            for field in ("net_income_history", "revenue_history", "dps_history"):
                v = row_data.get(field, [])
                row_data[field] = _json.dumps(v if isinstance(v, list) else [])
            row = pd.DataFrame([row_data])
            if FUNDAMENTALS_CSV.exists():
                existing = pd.read_csv(FUNDAMENTALS_CSV)
                existing = existing[existing["ticker"] != ticker]
                combined = pd.concat([existing, row], ignore_index=True)
            else:
                combined = row
            combined.to_csv(FUNDAMENTALS_CSV, index=False)
        except Exception as e:
            print(f"[DataLoader] fundamentals cache write failed: {e}")

    # ------------------------------------------------------------------ #
    #  Watchlist                                                           #
    # ------------------------------------------------------------------ #

    def get_watchlist(self) -> list:
        if WATCHLIST_JSON.exists():
            try:
                with open(WATCHLIST_JSON) as f:
                    import json as _json
                    return _json.load(f)
            except Exception:
                pass
        return []

    def add_to_watchlist(self, ticker: str) -> list:
        wl = self.get_watchlist()
        if ticker not in wl:
            wl.append(ticker)
            with open(WATCHLIST_JSON, "w") as f:
                import json as _json
                _json.dump(wl, f)
        return wl

    def remove_from_watchlist(self, ticker: str) -> list:
        wl = [t for t in self.get_watchlist() if t != ticker]
        with open(WATCHLIST_JSON, "w") as f:
            import json as _json
            _json.dump(wl, f)
        return wl

    # ------------------------------------------------------------------ #
    #  Missing data store                                                  #
    # ------------------------------------------------------------------ #

    def _load_missing(self) -> dict:
        if MISSING_JSON.exists():
            try:
                with open(MISSING_JSON) as f:
                    import json as _json
                    return _json.load(f)
            except Exception:
                pass
        return {}

    def _save_missing(self, data: dict):
        with open(MISSING_JSON, "w") as f:
            import json as _json
            _json.dump(data, f, indent=2)

    def save_missing_field(self, ticker: str, field_name: str, value, source: str):
        data = self._load_missing()
        if ticker not in data:
            data[ticker] = {}
        data[ticker][field_name] = {
            "value": value,
            "source": source,
            "created_at": datetime.now().isoformat(),
        }
        self._save_missing(data)

    def _inject_missing_data(self, ticker: str, fund: dict) -> dict:
        """Overlay any manually entered missing-data values onto the fund dict."""
        data = self._load_missing()
        overrides = data.get(ticker, {})
        if not overrides:
            return fund
        fund = dict(fund)
        for field, entry in overrides.items():
            fund[field] = entry["value"]
        return fund

    def get_missing_fields(self, ticker: str, fund: dict) -> list:
        """Return list of important fields that are None/missing for this stock."""
        important = [
            ("roe",               "ROE (Return on Equity)"),
            ("pe",                "P/E Ratio"),
            ("pb",                "P/B Ratio"),
            ("debt_to_equity",    "Debt-to-Equity ratio"),
            ("interest_coverage", "Interest Coverage Ratio"),
            ("total_assets",      "Total Assets"),
            ("market_cap",        "Market Cap"),
            ("net_income_history","5-Year Net Income History"),
            ("revenue_history",   "5-Year Revenue History"),
            ("dps_history",       "5-Year Dividend History"),
        ]
        missing = []
        for field, label in important:
            val = fund.get(field)
            if val is None or val == [] or val == 0:
                missing.append({"field": field, "label": label})
        return missing
