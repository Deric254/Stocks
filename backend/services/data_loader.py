"""
data_loader.py — read-side data layer over CSVDataManager, plus the watchlist
and manual single-field overrides. Thread-safe. Never crashes.
"""
import json
import threading
import pandas as pd
from datetime import datetime
from pathlib import Path

from services.csv_data_manager import get_manager, _price_of, _parse_history

from services.paths import DATA_DIR, seed_path
DATA_DIR.mkdir(parents=True, exist_ok=True)

WATCHLIST_JSON = DATA_DIR / "watchlist.json"
MISSING_JSON   = DATA_DIR / "missing_data.json"

_lock = threading.RLock()   # serialises every read-modify-write of the small JSON stores

# Fields a user may set by hand. Anything else (ticker, data_source, ...) is rejected
# so a manual entry can never overwrite bookkeeping fields.
OVERRIDABLE_FIELDS = frozenset({
    "eps", "bvps", "pe", "pb", "roe", "margin", "dividends", "dividend_yield", "market_cap",
    "total_assets", "debt_to_equity", "interest_coverage", "revenue", "net_income",
    "revenue_history", "net_income_history", "dps_history",
})


def _j(path, default):
    p = Path(path)
    if p.exists():
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            pass
    return default


def _w(path, data):
    """Atomic write (temp file + rename) so a crash never leaves a truncated JSON file."""
    with _lock:
        try:
            tmp = Path(path).with_suffix(".tmp")
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2, default=str)
            tmp.replace(path)
        except OSError as e:
            print(f"[DL] write error {path}: {e}")


def _load_seed() -> dict:
    path = seed_path()
    if path.exists():
        try:
            with open(path) as f:
                raw = json.load(f)
            return {k: v for k, v in raw.items() if not k.startswith("_")}
        except Exception:
            pass
    return {}


class DataLoader:
    def __init__(self):
        self._seed = _load_seed()

    def get_price_data(self, ticker: str) -> pd.DataFrame:
        mgr = get_manager()
        base = ticker.split(".")[0].upper()
        df = mgr.get_price_history_df(base, days=365)
        if not df.empty:
            return df
        price = _price_of(mgr.get_current_price(base))
        if price:
            idx = pd.DatetimeIndex([datetime.now()])
            return pd.DataFrame(
                {"open": [price], "high": [price], "low": [price],
                 "close": [price], "volume": [0]}, index=idx)
        seed_price = self._seed.get(base, {}).get("price", 0)
        if seed_price and seed_price > 0:
            idx = pd.DatetimeIndex([datetime.now()])
            return pd.DataFrame(
                {"open": [seed_price], "high": [seed_price],
                 "low": [seed_price], "close": [seed_price], "volume": [0]}, index=idx)
        return pd.DataFrame()

    def get_fundamentals(self, ticker: str) -> dict:
        mgr = get_manager()
        base = ticker.split(".")[0].upper()
        fund = mgr.get_fundamentals(base, seed=self._seed)
        return self._inject(base, fund)

    def get_data_freshness(self, tickers: list) -> list:
        mgr = get_manager()
        overrides = {t: {k: v["value"] for k, v in fields.items()}
                     for t, fields in _j(MISSING_JSON, {}).items()}
        return mgr.get_freshness_report(tickers, seed=self._seed, overrides=overrides)

    def get_watchlist(self):
        return _j(WATCHLIST_JSON, [])

    def add_to_watchlist(self, ticker: str):
        with _lock:
            wl = self.get_watchlist()
            if ticker not in wl:
                wl.append(ticker)
                _w(WATCHLIST_JSON, wl)
            return wl

    def remove_from_watchlist(self, ticker: str):
        with _lock:
            wl = [x for x in self.get_watchlist() if x != ticker]
            _w(WATCHLIST_JSON, wl)
            return wl

    def save_missing_field(self, ticker: str, field: str, value, source: str):
        base = ticker.split(".")[0].upper()
        if field not in OVERRIDABLE_FIELDS:
            raise ValueError(f"'{field}' cannot be set manually")
        if field.endswith("_history"):
            value = _parse_history(value)   # "1;2;3" -> [1.0, 2.0, 3.0]; consumers expect a list
        with _lock:
            d = _j(MISSING_JSON, {})
            d.setdefault(base, {})[field] = {"value": value, "source": source,
                                             "created_at": datetime.now().isoformat()}
            _w(MISSING_JSON, d)

    def _inject(self, base: str, fund: dict) -> dict:
        ov = _j(MISSING_JSON, {}).get(base, {})
        if not ov:
            return fund
        fund = dict(fund)
        for k, v in ov.items():
            fund[k] = v["value"]
        return fund

    def get_missing_fields(self, ticker: str, fund: dict) -> list:
        fields = [
            ("roe", "ROE"), ("pe", "P/E"), ("pb", "P/B"),
            ("debt_to_equity", "D/E"), ("interest_coverage", "Interest Coverage"),
            ("total_assets", "Total Assets"), ("market_cap", "Market Cap"),
            ("net_income_history", "5yr Net Income"),
            ("revenue_history", "5yr Revenue"), ("dps_history", "5yr Dividends"),
        ]
        return [{"field": f, "label": l} for f, l in fields
                if not fund.get(f) or fund.get(f) == []]
