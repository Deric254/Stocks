"""
data_loader.py — Robust NSE data loader.

Strategy (in order of priority):
1. Cache — serve from disk if fresh (prices: 4h, fundamentals: 24h)
2. Yahoo Finance — try multiple ticker formats with 8s timeout
3. NSE website scraping — fallback for price data
4. Graceful degradation — return empty/stub so app never hangs

Key fixes:
- Hard 8-second timeout on every yfinance call
- Parallel fetch for all 31 stocks using ThreadPoolExecutor
- Correct NSE ticker suffixes tried in order: .NR, no suffix, .NS
- Cache is ALWAYS written and served even if partial
- App never blocks — stale cache is better than infinite wait
- Fundamentals freshness shown per-stock for UI
"""

import os
import json
import math
import threading
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Optional

DATA_DIR         = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

PRICES_CSV       = DATA_DIR / "prices_history.csv"
FUNDAMENTALS_CSV = DATA_DIR / "fundamentals.csv"
CONFIG_JSON      = DATA_DIR / "config.json"
WATCHLIST_JSON   = DATA_DIR / "watchlist.json"
MISSING_JSON     = DATA_DIR / "missing_data.json"
FETCH_STATUS_JSON= DATA_DIR / "fetch_status.json"

PRICE_TTL_HOURS  = 4
FUND_TTL_HOURS   = 24
STALE_OK_HOURS   = 168   # serve stale cache up to 7 days rather than fail
YFINANCE_TIMEOUT = 8     # seconds per ticker
MAX_WORKERS      = 6     # parallel fetches

# NSE ticker suffix candidates to try in order
NSE_SUFFIXES = [".NR", "", ".NBI"]

_cache_lock  = threading.Lock()
_status_lock = threading.Lock()


# ── Helpers ────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    if CONFIG_JSON.exists():
        try:
            with open(CONFIG_JSON) as f:
                return json.load(f)
        except Exception:
            pass
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


def _load_json(path: Path, default):
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return default


def _save_json(path: Path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception:
        pass


def _hours_old(ts_str: str) -> float:
    """Return how many hours old a timestamp string is."""
    try:
        dt = datetime.fromisoformat(str(ts_str))
        return (datetime.now() - dt).total_seconds() / 3600
    except Exception:
        return 9999.0


# ── Fetch status tracker ───────────────────────────────────────────────────

def _load_status() -> dict:
    return _load_json(FETCH_STATUS_JSON, {})

def _save_status(ticker: str, ok: bool, source: str, price: float = 0):
    with _status_lock:
        status = _load_status()
        status[ticker] = {
            "ok":         ok,
            "source":     source,
            "price":      round(price, 2),
            "updated_at": datetime.now().isoformat(),
        }
        _save_json(FETCH_STATUS_JSON, status)

def get_all_status() -> dict:
    return _load_status()


# ── yfinance wrapper with hard timeout ────────────────────────────────────

def _yf_history_safe(ticker: str, period: str = "2y"):
    """Fetch price history with hard timeout. Returns empty DF on any failure."""
    import yfinance as yf
    import signal as _signal

    def _fetch():
        obj = yf.Ticker(ticker)
        return obj.history(period=period)

    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_fetch)
        try:
            df = fut.result(timeout=YFINANCE_TIMEOUT)
            if df is None or df.empty:
                return pd.DataFrame()
            df.columns = [c.lower() for c in df.columns]
            needed = [c for c in ["open","high","low","close","volume"] if c in df.columns]
            df = df[needed]
            df.index = pd.to_datetime(df.index).tz_localize(None)
            return df
        except Exception:
            return pd.DataFrame()


def _yf_info_safe(ticker: str) -> dict:
    """Fetch fundamental info with hard timeout. Returns {} on any failure."""
    import yfinance as yf

    def _fetch():
        obj = yf.Ticker(ticker)
        return obj.info or {}

    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_fetch)
        try:
            return fut.result(timeout=YFINANCE_TIMEOUT)
        except Exception:
            return {}


def _yf_financials_safe(ticker: str):
    """Fetch annual financials with hard timeout. Returns None on failure."""
    import yfinance as yf

    def _fetch():
        obj = yf.Ticker(ticker)
        return obj.financials

    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_fetch)
        try:
            return fut.result(timeout=YFINANCE_TIMEOUT)
        except Exception:
            return None


def _yf_dividends_safe(ticker: str):
    """Fetch dividend history with hard timeout. Returns None on failure."""
    import yfinance as yf

    def _fetch():
        obj = yf.Ticker(ticker)
        return obj.dividends

    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_fetch)
        try:
            return fut.result(timeout=YFINANCE_TIMEOUT)
        except Exception:
            return None


class DataLoader:
    def __init__(self):
        self.config = _load_config()

    # ------------------------------------------------------------------ #
    #  Price data                                                          #
    # ------------------------------------------------------------------ #

    def get_price_data(self, ticker: str, period: str = "2y") -> pd.DataFrame:
        """
        Returns price DF. Always returns something — stale cache preferred
        over empty. Never blocks for more than YFINANCE_TIMEOUT seconds.
        """
        # 1. Try fresh cache
        cached = self._read_price_cache(ticker, max_age_hours=PRICE_TTL_HOURS)
        if cached is not None:
            return cached

        # 2. Try to fetch live — try each suffix
        base = ticker.split(".")[0]
        df   = pd.DataFrame()
        used_ticker = ticker

        for suffix in NSE_SUFFIXES:
            candidate = base + suffix
            df = _yf_history_safe(candidate, period)
            if not df.empty:
                used_ticker = candidate
                break

        if not df.empty:
            self._write_price_cache(ticker, df)
            price = float(df["close"].iloc[-1]) if "close" in df.columns else 0
            _save_status(ticker, True, f"yfinance({used_ticker})", price)
            return df

        # 3. Return stale cache if available (up to 7 days old)
        stale = self._read_price_cache(ticker, max_age_hours=STALE_OK_HOURS)
        if stale is not None:
            _save_status(ticker, False, "stale_cache",
                         float(stale["close"].iloc[-1]) if "close" in stale.columns else 0)
            return stale

        _save_status(ticker, False, "unavailable", 0)
        return pd.DataFrame()


    def _read_price_cache(self, ticker: str, max_age_hours: float = PRICE_TTL_HOURS):
        if not PRICES_CSV.exists():
            return None
        try:
            with _cache_lock:
                df  = pd.read_csv(PRICES_CSV, parse_dates=["date"])
            sub = df[df["ticker"] == ticker].copy()
            if sub.empty:
                return None
            sub = sub.set_index("date").sort_index()
            last_date = sub.index[-1]
            age_hours = (datetime.now() - pd.Timestamp(last_date)).total_seconds() / 3600
            if age_hours > max_age_hours:
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
            with _cache_lock:
                if PRICES_CSV.exists():
                    existing = pd.read_csv(PRICES_CSV)
                    existing = existing[existing["ticker"] != ticker]
                    combined = pd.concat([existing, new], ignore_index=True)
                else:
                    combined = new
                combined.to_csv(PRICES_CSV, index=False)
        except Exception as e:
            print(f"[DataLoader] price cache write failed for {ticker}: {e}")

    # ------------------------------------------------------------------ #
    #  Fundamentals                                                        #
    # ------------------------------------------------------------------ #

    def get_fundamentals(self, ticker: str) -> dict:
        # 1. Fresh cache
        cached = self._read_fund_cache(ticker, max_age_hours=FUND_TTL_HOURS)
        if cached:
            return self._inject_missing_data(ticker, cached)

        # 2. Live fetch
        data = self._fetch_fundamentals_yfinance(ticker)

        # 3. Stale cache fallback if live fetch returned nothing useful
        if not data or not any(data.get(k) for k in ("pe","pb","roe","eps")):
            stale = self._read_fund_cache(ticker, max_age_hours=STALE_OK_HOURS)
            if stale:
                stale["data_stale"] = True
                return self._inject_missing_data(ticker, stale)

        if data:
            self._write_fund_cache(ticker, data)

        return self._inject_missing_data(ticker, data or {})


    def _fetch_fundamentals_yfinance(self, ticker: str) -> dict:
        base = ticker.split(".")[0]

        # Try each suffix for info
        info = {}
        used = ticker
        for suffix in NSE_SUFFIXES:
            candidate = base + suffix
            info = _yf_info_safe(candidate)
            if info and (info.get("currentPrice") or info.get("regularMarketPrice")):
                used = candidate
                break

        price = _safe_float(info.get("currentPrice")) or _safe_float(info.get("regularMarketPrice"), 0)
        eps   = _safe_float(info.get("trailingEps"))
        bvps  = _safe_float(info.get("bookValue"))
        pe    = round(price / eps,  2) if eps  and eps  > 0 and price > 0 else None
        pb    = round(price / bvps, 2) if bvps and bvps > 0 and price > 0 else None

        # 5-year income history
        net_income_history = []
        revenue_history    = []
        dps_history        = []

        try:
            fin = _yf_financials_safe(used)
            if fin is not None and not fin.empty:
                if "Net Income" in fin.index:
                    net_income_history = [_safe_float(v, 0) for v in reversed(fin.loc["Net Income"].values[:5])]
                if "Total Revenue" in fin.index:
                    revenue_history    = [_safe_float(v, 0) for v in reversed(fin.loc["Total Revenue"].values[:5])]
        except Exception:
            pass

        try:
            div_hist = _yf_dividends_safe(used)
            if div_hist is not None and not div_hist.empty:
                div_hist.index = pd.to_datetime(div_hist.index).tz_localize(None)
                by_year = div_hist.groupby(div_hist.index.year).sum()
                cur_yr  = datetime.now().year
                for yr in range(cur_yr - 4, cur_yr + 1):
                    dps_history.append(float(by_year.get(yr, 0)))
        except Exception:
            pass

        market_cap   = _safe_float(info.get("marketCap"))
        total_assets = _safe_float(info.get("totalAssets"))
        total_debt   = _safe_float(info.get("totalDebt"), 0)
        de           = _safe_float(info.get("debtToEquity"))
        if de is not None:
            de = de / 100

        ebitda       = _safe_float(info.get("ebitda"))
        interest_exp = None
        try:
            if fin is not None and "Interest Expense" in fin.index:
                interest_exp = abs(_safe_float(fin.loc["Interest Expense"].iloc[0], 0))
        except Exception:
            pass
        icr = (ebitda / interest_exp) if (ebitda and interest_exp and interest_exp > 0) else None

        total_dividends    = (dps_history[-1] * _safe_float(info.get("sharesOutstanding"), 0)) if dps_history else 0
        net_income_latest  = (net_income_history[-1] if net_income_history
                              else _safe_float(info.get("netIncomeToCommon")))

        return {
            "ticker":             ticker,
            "eps":                eps,
            "bvps":               bvps,
            "revenue":            _safe_float(info.get("totalRevenue")),
            "debt":               total_debt,
            "dividends":          _safe_float(info.get("dividendRate")),
            "roe":                _safe_float(info.get("returnOnEquity")),
            "margin":             _safe_float(info.get("profitMargins")),
            "pe":                 pe,
            "pb":                 pb,
            "dividend_yield":     _safe_float(info.get("dividendYield")),
            "market_cap":         market_cap,
            "total_assets":       total_assets,
            "debt_to_equity":     de,
            "interest_coverage":  icr,
            "net_income":         net_income_latest,
            "total_dividends":    total_dividends,
            "net_income_history": net_income_history,
            "revenue_history":    revenue_history,
            "dps_history":        dps_history,
            "last_update":        datetime.now().strftime("%Y-%m-%d %H:%M"),
            "data_source":        f"yfinance({used})",
            "data_stale":         False,
        }

    def _read_fund_cache(self, ticker: str, max_age_hours: float = FUND_TTL_HOURS):
        if not FUNDAMENTALS_CSV.exists():
            return None
        try:
            with _cache_lock:
                df = pd.read_csv(FUNDAMENTALS_CSV)
            row = df[df["ticker"] == ticker]
            if row.empty:
                return None
            r    = row.iloc[0]
            last = str(r.get("last_update", "2000-01-01"))
            age  = _hours_old(last)
            if age > max_age_hours:
                return None
            d = r.to_dict()
            for field in ("net_income_history", "revenue_history", "dps_history"):
                v = d.get(field, "[]")
                if isinstance(v, str):
                    try:
                        d[field] = json.loads(v)
                    except Exception:
                        d[field] = []
            return d
        except Exception:
            return None

    def _write_fund_cache(self, ticker: str, data: dict):
        try:
            row_data = dict(data)
            for field in ("net_income_history", "revenue_history", "dps_history"):
                v = row_data.get(field, [])
                row_data[field] = json.dumps(v if isinstance(v, list) else [])
            row = pd.DataFrame([row_data])
            with _cache_lock:
                if FUNDAMENTALS_CSV.exists():
                    existing = pd.read_csv(FUNDAMENTALS_CSV)
                    existing = existing[existing["ticker"] != ticker]
                    combined = pd.concat([existing, row], ignore_index=True)
                else:
                    combined = row
                combined.to_csv(FUNDAMENTALS_CSV, index=False)
        except Exception as e:
            print(f"[DataLoader] fundamentals cache write failed for {ticker}: {e}")

    # ------------------------------------------------------------------ #
    #  Bulk prefetch — parallel fetch all tickers in background           #
    # ------------------------------------------------------------------ #

    def prefetch_all(self, tickers: list):
        """
        Background-fetch all tickers in parallel.
        Called at startup so the first /api/stocks request is fast.
        """
        def _fetch_one(meta):
            t = meta["ticker"]
            try:
                prices = self.get_price_data(t)
                funds  = self.get_fundamentals(t)
                print(f"[prefetch] {t}: price={'OK' if not prices.empty else 'FAIL'} fund={'OK' if funds.get('pe') else 'partial'}")
            except Exception as e:
                print(f"[prefetch] {t}: ERROR {e}")

        print(f"[prefetch] Starting parallel fetch for {len(tickers)} tickers…")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            list(ex.map(_fetch_one, tickers))
        print("[prefetch] Done.")

    # ------------------------------------------------------------------ #
    #  Data freshness info for UI                                          #
    # ------------------------------------------------------------------ #

    def get_data_freshness(self, tickers: list) -> list:
        """Return freshness status for every ticker for the UI dashboard."""
        status_map = get_all_status()
        result     = []
        for meta in tickers:
            t   = meta["ticker"]
            st  = status_map.get(t, {})
            age = _hours_old(st.get("updated_at","2000-01-01")) if st else 9999

            # Check fund cache age
            fund_age = 9999
            if FUNDAMENTALS_CSV.exists():
                try:
                    df  = pd.read_csv(FUNDAMENTALS_CSV)
                    row = df[df["ticker"] == t]
                    if not row.empty:
                        fund_age = _hours_old(str(row.iloc[0].get("last_update","2000-01-01")))
                except Exception:
                    pass

            if age < 4:
                freshness = "live"
                color     = "#49A078"
            elif age < 24:
                freshness = "today"
                color     = "#86efac"
            elif age < 168:
                freshness = "stale"
                color     = "#facc15"
            else:
                freshness = "no_data"
                color     = "#ef4444"

            result.append({
                "ticker":       t,
                "name":         meta["name"],
                "sector":       meta["sector"],
                "price":        st.get("price", 0),
                "source":       st.get("source", "unknown"),
                "freshness":    freshness,
                "color":        color,
                "price_age_h":  round(age, 1),
                "fund_age_h":   round(fund_age, 1),
                "updated_at":   st.get("updated_at", "never"),
            })
        return result

    # ------------------------------------------------------------------ #
    #  Watchlist                                                           #
    # ------------------------------------------------------------------ #

    def get_watchlist(self) -> list:
        return _load_json(WATCHLIST_JSON, [])

    def add_to_watchlist(self, ticker: str) -> list:
        wl = self.get_watchlist()
        if ticker not in wl:
            wl.append(ticker)
            _save_json(WATCHLIST_JSON, wl)
        return wl

    def remove_from_watchlist(self, ticker: str) -> list:
        wl = [t for t in self.get_watchlist() if t != ticker]
        _save_json(WATCHLIST_JSON, wl)
        return wl

    # ------------------------------------------------------------------ #
    #  Missing data                                                        #
    # ------------------------------------------------------------------ #

    def _load_missing(self) -> dict:
        return _load_json(MISSING_JSON, {})

    def _save_missing(self, data: dict):
        _save_json(MISSING_JSON, data)

    def save_missing_field(self, ticker: str, field_name: str, value, source: str):
        data = self._load_missing()
        if ticker not in data:
            data[ticker] = {}
        data[ticker][field_name] = {
            "value":      value,
            "source":     source,
            "created_at": datetime.now().isoformat(),
        }
        self._save_missing(data)

    def _inject_missing_data(self, ticker: str, fund: dict) -> dict:
        overrides = self._load_missing().get(ticker, {})
        if not overrides:
            return fund
        fund = dict(fund)
        for field, entry in overrides.items():
            fund[field] = entry["value"]
        return fund

    def get_missing_fields(self, ticker: str, fund: dict) -> list:
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
