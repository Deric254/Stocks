"""
data_loader.py — NSE data loader using nse_scraper (NOT Yahoo Finance).

Yahoo Finance does not cover NSE Kenya. This loader uses:
  1. nse_scraper.py — real NSE website + African Markets sources
  2. JSON-based cache (not CSV — more robust, no "No columns" errors)
  3. Manual data entry overlay
  4. Always returns something — never hangs

Cache files (JSON, in backend/data/):
  prices_cache.json      — {TICKER: {price, source, updated_at}}
  fundamentals_cache.json — {TICKER: {pe, pb, roe, ...}}
  watchlist.json
  missing_data.json
  fetch_status.json
"""

import json
import math
import threading
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
import pandas as pd

from services.nse_scraper import (
    get_price, get_all_prices, get_price_history,
    get_fundamentals as scrape_fundamentals,
    MANUAL_PRICE_STUBS,
)

DATA_DIR          = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

WATCHLIST_JSON    = DATA_DIR / "watchlist.json"
MISSING_JSON      = DATA_DIR / "missing_data.json"
FETCH_STATUS_JSON = DATA_DIR / "fetch_status.json"
CONFIG_JSON       = DATA_DIR / "config.json"

_lock = threading.Lock()


def _load_json(path: Path, default):
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return default

def _save_json(path: Path, data):
    with _lock:
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            print(f"[DataLoader] save failed {path.name}: {e}")

def _safe_float(val, default=None):
    if val is None: return default
    try:
        f = float(val)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except: return default

def _hours_old(ts_str) -> float:
    try:
        dt = datetime.fromisoformat(str(ts_str))
        return (datetime.now() - dt).total_seconds() / 3600
    except: return 9999.0


class DataLoader:
    def __init__(self):
        self.config = _load_json(CONFIG_JSON, {})

    # ------------------------------------------------------------------ #
    #  Price data                                                          #
    # ------------------------------------------------------------------ #

    def get_price_data(self, ticker: str, period: str = "2y") -> pd.DataFrame:
        """Returns OHLCV DataFrame. Uses NSE scraper, never Yahoo Finance."""
        base = ticker.split(".")[0].upper()
        try:
            df = get_price_history(ticker, days=365)
            if df is not None and not df.empty:
                price = float(df["close"].iloc[-1]) if "close" in df.columns else 0
                self._save_status(base, True, "nse_scraper", price)
                return df
        except Exception as e:
            print(f"[DataLoader] price history failed for {base}: {e}")

        # Minimal single-row stub so rest of app works
        p = get_price(ticker).get("price", 0)
        self._save_status(base, False, "stub", p)
        if p > 0:
            idx = pd.DatetimeIndex([datetime.now()])
            return pd.DataFrame({
                "open":[p],"high":[p],"low":[p],"close":[p],"volume":[0]
            }, index=idx)
        return pd.DataFrame()

    def get_fundamentals(self, ticker: str) -> dict:
        """Returns fundamentals dict, with manual overrides applied."""
        base = ticker.split(".")[0].upper()
        try:
            fund = scrape_fundamentals(ticker)
            if fund:
                return self._inject_missing_data(base, fund)
        except Exception as e:
            print(f"[DataLoader] fundamentals failed for {base}: {e}")
        return self._inject_missing_data(base, {
            "ticker": ticker, "data_stale": True, "data_source": "none",
            "eps": None, "bvps": None, "revenue": None, "debt": None,
            "dividends": None, "roe": None, "margin": None,
            "pe": None, "pb": None, "dividend_yield": None,
            "market_cap": None, "total_assets": None,
            "debt_to_equity": None, "interest_coverage": None,
            "net_income": None, "total_dividends": None,
            "net_income_history": [], "revenue_history": [], "dps_history": [],
            "last_update": "never",
        })

    # ------------------------------------------------------------------ #
    #  Bulk prefetch                                                       #
    # ------------------------------------------------------------------ #

    def prefetch_all(self, tickers: list):
        """Parallel prefetch of all NSE tickers. Called at startup."""
        # Bulk price fetch first (one HTTP call for all stocks)
        print(f"[prefetch] Fetching all NSE prices in bulk…")
        try:
            all_prices = get_all_prices()
            print(f"[prefetch] Got prices for {len(all_prices)} stocks")
        except Exception as e:
            print(f"[prefetch] Bulk price fetch failed: {e}")

        # Fundamentals fetched in parallel (slower, one per stock)
        def _fetch_fund(meta):
            t = meta["ticker"]
            base = t.split(".")[0].upper()
            try:
                fund = scrape_fundamentals(t)
                print(f"[prefetch] {base}: fund={'OK' if fund.get('pe') or fund.get('eps') else 'partial/none'}")
            except Exception as e:
                print(f"[prefetch] {base}: fund error {e}")

        print(f"[prefetch] Fetching fundamentals for {len(tickers)} stocks…")
        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(_fetch_fund, tickers))
        print("[prefetch] Done.")

    # ------------------------------------------------------------------ #
    #  Data freshness                                                      #
    # ------------------------------------------------------------------ #

    def _save_status(self, base: str, ok: bool, source: str, price: float = 0):
        status = _load_json(FETCH_STATUS_JSON, {})
        status[base] = {
            "ok": ok, "source": source,
            "price": round(price, 2),
            "updated_at": datetime.now().isoformat(),
        }
        _save_json(FETCH_STATUS_JSON, status)

    def get_data_freshness(self, tickers: list) -> list:
        status_map = _load_json(FETCH_STATUS_JSON, {})
        price_cache = _load_json(DATA_DIR / "nse_cache" / "prices.json", {})
        fund_cache  = _load_json(DATA_DIR / "nse_cache" / "fundamentals.json", {})
        result = []

        for meta in tickers:
            t    = meta["ticker"]
            base = t.split(".")[0].upper()
            st   = status_map.get(base, {})
            pc   = price_cache.get(base, {})
            fc   = fund_cache.get(base, {})

            price_age = _hours_old(pc.get("updated_at","2000-01-01")) if pc else 9999
            fund_age  = _hours_old(fc.get("last_update","2000-01-01")) if fc else 9999
            price_val = pc.get("price", 0) or st.get("price", 0)
            source    = pc.get("source", st.get("source","unknown"))

            if price_age < 4:
                freshness, color = "live",    "#49A078"
            elif price_age < 24:
                freshness, color = "today",   "#86efac"
            elif price_age < 168:
                freshness, color = "stale",   "#facc15"
            else:
                freshness, color = "no_data", "#ef4444"

            # If source is manual_stub, always show as no_data
            if source == "manual_stub":
                freshness, color = "no_data", "#ef4444"

            result.append({
                "ticker":      t,
                "name":        meta["name"],
                "sector":      meta["sector"],
                "price":       price_val,
                "source":      source,
                "freshness":   freshness,
                "color":       color,
                "price_age_h": round(price_age, 1),
                "fund_age_h":  round(fund_age, 1),
                "updated_at":  pc.get("updated_at", "never"),
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

    def _inject_missing_data(self, base: str, fund: dict) -> dict:
        overrides = _load_json(MISSING_JSON, {}).get(base, {})
        if not overrides:
            return fund
        fund = dict(fund)
        for field, entry in overrides.items():
            fund[field] = entry["value"]
        return fund

    def save_missing_field(self, ticker: str, field_name: str, value, source: str):
        base = ticker.split(".")[0].upper()
        data = _load_json(MISSING_JSON, {})
        if base not in data:
            data[base] = {}
        data[base][field_name] = {
            "value": value, "source": source,
            "created_at": datetime.now().isoformat(),
        }
        _save_json(MISSING_JSON, data)

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
        return [
            {"field": f, "label": l}
            for f, l in important
            if not fund.get(f) or fund.get(f) == []
        ]
