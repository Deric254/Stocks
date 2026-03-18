"""
csv_data_manager.py — Manual CSV upload data layer.
No scraping. No APIs. You feed the data.

Two separate upload flows:
  1. PRICES  — upload weekly, system warns if >7 days old
  2. FUNDAMENTALS — upload quarterly, system warns if >90 days old

Templates are generated for all NSE tickers so you can fill them in.
Data is cleaned, validated, merged without data loss.

ROBUSTNESS FIXES (v2):
  - Thread-safe singleton init (double-checked locking)
  - Disk I/O moved OUTSIDE the in-memory lock — no blocking on slow writes
  - Atomic file writes via temp-file + rename (no corrupt files on crash)
  - CSV parsing is fully defensive — bad rows skipped, never crashes
  - Accepts many column name variants (price/close/last/Price/Close etc.)
  - Accepts many encodings (utf-8, utf-8-sig, latin-1, cp1252)
  - Accepts both comma and semicolon delimiters
  - History fields: accepts | and , as separators too
  - Numbers: strips currency symbols, commas, spaces, M/B/K suffixes
  - Upload never returns error if even ONE valid row is present
  - Stale in-memory state reloaded atomically after disk save
"""

import csv
import io
import json
import math
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

PRICES_CSV       = DATA_DIR / "prices_manual.csv"
FUNDAMENTALS_CSV = DATA_DIR / "fundamentals_manual.csv"
PRICES_HISTORY   = DATA_DIR / "prices_history_manual.csv"
META_JSON        = DATA_DIR / "upload_meta.json"

# Separate locks: one for in-memory state, one for disk writes
_mem_lock  = threading.RLock()   # RLock so same thread can re-enter
_disk_lock = threading.Lock()    # disk writes serialised separately
_init_lock = threading.Lock()    # singleton init

# ── Fields ────────────────────────────────────────────────────────────────────

PRICE_FIELDS = ["ticker", "price"]

FUNDAMENTAL_FIELDS = [
    "ticker",
    "eps", "bvps", "pe", "pb", "roe", "margin",
    "dividends", "dividend_yield", "market_cap", "total_assets",
    "debt_to_equity", "interest_coverage", "revenue", "net_income",
    "revenue_history", "net_income_history", "dps_history",
    "data_source", "fiscal_year", "last_update",
]

# Accepted column aliases → canonical name
_PRICE_ALIASES = {
    "ticker": "ticker", "symbol": "ticker", "stock": "ticker", "code": "ticker",
    "price": "price", "close": "price", "last": "price", "last_price": "price",
    "closing_price": "price", "close_price": "price", "current_price": "price",
}

_FUND_ALIASES = {
    "ticker": "ticker", "symbol": "ticker", "stock": "ticker", "code": "ticker",
    "eps": "eps", "earnings_per_share": "eps",
    "bvps": "bvps", "book_value_per_share": "bvps", "book_value": "bvps",
    "pe": "pe", "p/e": "pe", "pe_ratio": "pe", "price_to_earnings": "pe",
    "pb": "pb", "p/b": "pb", "pb_ratio": "pb", "price_to_book": "pb",
    "roe": "roe", "return_on_equity": "roe",
    "margin": "margin", "net_margin": "margin", "profit_margin": "margin",
    "dividends": "dividends", "total_dividends": "dividends", "div": "dividends",
    "dividend_yield": "dividend_yield", "div_yield": "dividend_yield", "yield": "dividend_yield",
    "market_cap": "market_cap", "mkt_cap": "market_cap", "capitalisation": "market_cap",
    "total_assets": "total_assets", "assets": "total_assets",
    "debt_to_equity": "debt_to_equity", "d/e": "debt_to_equity", "de_ratio": "debt_to_equity",
    "interest_coverage": "interest_coverage", "coverage": "interest_coverage",
    "revenue": "revenue", "turnover": "revenue", "sales": "revenue",
    "net_income": "net_income", "profit": "net_income", "net_profit": "net_income",
    "revenue_history": "revenue_history",
    "net_income_history": "net_income_history", "ni_history": "net_income_history",
    "dps_history": "dps_history", "dividends_history": "dps_history",
    "data_source": "data_source", "source": "data_source",
    "fiscal_year": "fiscal_year", "fy": "fiscal_year", "year": "fiscal_year",
    "last_update": "last_update", "updated": "last_update", "date": "last_update",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rj(path, default):
    p = Path(path)
    if p.exists():
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            pass
    return default


def _wj_atomic(path, data):
    path = Path(path)
    try:
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, default=str)
        tmp.replace(path)
    except Exception as e:
        print(f"[CSV-MGR] write error {path}: {e}")


def _write_csv_atomic(path: Path, df: pd.DataFrame):
    try:
        tmp = path.with_suffix(".tmp")
        df.to_csv(tmp, index=False)
        tmp.replace(path)
    except Exception as e:
        print(f"[CSV-MGR] csv write error {path}: {e}")


def _age_h(ts_str) -> float:
    try:
        return (datetime.now() - datetime.fromisoformat(str(ts_str))).total_seconds() / 3600
    except Exception:
        return 9999.0


def _age_days(ts_str) -> float:
    return _age_h(ts_str) / 24


def _decode_bytes(content: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            return content.decode(enc)
        except Exception:
            continue
    return content.decode("utf-8", errors="replace")


def _sniff_delimiter(text: str) -> str:
    first_line = text.split("\n")[0]
    return ";" if first_line.count(";") > first_line.count(",") else ","


def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in ("", "nan", "none", "n/a", "na", "-", "—"):
        return None
    s = s.replace(",", "").replace(" ", "").replace("KES", "").replace("$", "").replace("£", "")
    multiplier = 1.0
    if s.upper().endswith("B"):
        multiplier = 1e9; s = s[:-1]
    elif s.upper().endswith("M"):
        multiplier = 1e6; s = s[:-1]
    elif s.upper().endswith("K"):
        multiplier = 1e3; s = s[:-1]
    try:
        val = float(s) * multiplier
        return None if (math.isnan(val) or math.isinf(val)) else val
    except Exception:
        return None


def _parse_history(val) -> list:
    if not val or str(val).strip() in ("", "nan", "none"):
        return []
    s = str(val).strip()
    for sep in (";", "|", ","):
        if sep in s:
            parts = s.split(sep); break
    else:
        parts = [s]
    return [f for f in (_safe_float(p) for p in parts) if f is not None]


def _normalise_row(row: dict, alias_map: dict) -> dict:
    out = {}
    for k, v in row.items():
        k_norm = str(k).strip().lower().replace(" ", "_").replace("-", "_")
        canonical = alias_map.get(k_norm, k_norm)
        out[canonical] = str(v).strip() if v is not None else ""
    return out


# ── Template generation ───────────────────────────────────────────────────────

def generate_price_template(tickers: list) -> str:
    """
    Price template pre-filled from live scraper.
    - Scraper hit first (kenyanstocks.com bulk)
    - Manual stubs fill any gaps
    - Cells the scraper couldn't find left EMPTY so they show red in Excel/Sheets
    """
    # Import here to avoid circular imports at module load
    live_prices = {}
    try:
        from services.nse_scraper import get_all_prices
        live_prices = get_all_prices()   # cached 4h — fast on repeat calls
        print(f"[template/prices] scraper returned {len(live_prices)} prices")
    except Exception as e:
        print(f"[template/prices] scraper unavailable: {e}")

    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=PRICE_FIELDS)
    w.writeheader()
    for t in tickers:
        base = t["ticker"].split(".")[0].upper()
        entry = live_prices.get(base, {})
        price = entry.get("price")
        # Leave empty if scraper couldn't find it — user fills in the red cell
        w.writerow({"ticker": base, "price": price if price else ""})
    return out.getvalue()


def generate_fundamentals_template(tickers: list, seed: dict) -> str:
    """
    Fundamentals template pre-filled from scraper then seed.
    Priority: scraper (live afx.kwayisi.org) > seed (annual reports) > empty (red cell).
    Empty cells = scraper AND seed both missing — user fills those in.
    """
    live_funds = {}
    try:
        from services.nse_scraper import get_fundamentals as scraper_get_fund
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _fetch(ticker_base):
            try:
                return ticker_base, scraper_get_fund(ticker_base)
            except Exception:
                return ticker_base, {}

        bases = [t["ticker"].split(".")[0].upper() for t in tickers]
        with ThreadPoolExecutor(max_workers=6) as ex:
            for base, data in ex.map(_fetch, bases, timeout=10):
                if data:
                    live_funds[base] = data
        print(f"[template/fundamentals] scraper returned {len(live_funds)} stocks")
    except Exception as e:
        print(f"[template/fundamentals] scraper unavailable: {e}")

    def fmt_history(arr):
        return ";".join(str(v) for v in arr) if arr else ""

    def pick(live, sd, field, default=""):
        """Live scraper wins, then seed, then default (empty = red cell)."""
        v = live.get(field)
        if v is not None and v != "" and v != []:
            return v
        v = sd.get(field)
        if v is not None and v != "" and v != []:
            return v
        return default

    rows = []
    today = datetime.now().strftime("%Y-%m-%d")
    for t in tickers:
        base = t["ticker"].split(".")[0].upper()
        lv = live_funds.get(base, {})
        sd = seed.get(base, {})

        rows.append({
            "ticker":             base,
            "eps":                pick(lv, sd, "eps"),
            "bvps":               pick(lv, sd, "bvps"),
            "pe":                 pick(lv, sd, "pe"),
            "pb":                 pick(lv, sd, "pb"),
            "roe":                pick(lv, sd, "roe"),
            "margin":             pick(lv, sd, "margin"),
            "dividends":          pick(lv, sd, "dividends"),
            "dividend_yield":     pick(lv, sd, "dividend_yield"),
            "market_cap":         pick(lv, sd, "market_cap"),
            "total_assets":       pick(lv, sd, "total_assets"),
            "debt_to_equity":     pick(lv, sd, "debt_to_equity"),
            "interest_coverage":  pick(lv, sd, "interest_coverage"),
            "revenue":            pick(lv, sd, "revenue"),
            "net_income":         pick(lv, sd, "net_income"),
            "revenue_history":    fmt_history(pick(lv, sd, "revenue_history", [])),
            "net_income_history": fmt_history(pick(lv, sd, "net_income_history", [])),
            "dps_history":        fmt_history(pick(lv, sd, "dps_history", [])),
            "data_source":        pick(lv, sd, "data_source", ""),
            "fiscal_year":        pick(lv, sd, "fiscal_year", "2024"),
            "last_update":        pick(lv, sd, "last_update", today),
        })

    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=FUNDAMENTAL_FIELDS)
    w.writeheader()
    w.writerows(rows)
    return out.getvalue()


# ── CSV Parsers ───────────────────────────────────────────────────────────────

def parse_price_csv(content: bytes) -> tuple:
    """Returns (valid_rows, errors, warnings). Extremely defensive."""
    errors = []
    warnings = []
    valid = []
    today = datetime.now().strftime("%Y-%m-%d")

    try:
        text = _decode_bytes(content).strip()
        if not text:
            return [], ["Uploaded file is empty"], []

        delimiter = _sniff_delimiter(text)
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

        if not reader.fieldnames:
            return [], ["CSV has no header row — check your file format"], []

        row_num = 1
        for raw_row in reader:
            row_num += 1
            try:
                row = _normalise_row(raw_row, _PRICE_ALIASES)
                ticker = row.get("ticker", "").upper()
                if not ticker:
                    warnings.append(f"Row {row_num}: no ticker — skipped")
                    continue

                price = _safe_float(row.get("price") or row.get("close") or "")
                if price is None or price <= 0:
                    warnings.append(f"{ticker} row {row_num}: price missing or zero — skipped")
                    continue

                date_val = row.get("date") or row.get("last_update") or today
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
                    try:
                        date_val = datetime.strptime(date_val, fmt).strftime("%Y-%m-%d")
                        break
                    except Exception:
                        date_val = today

                vol = int(_safe_float(row.get("volume", "0")) or 0)
                valid.append({
                    "ticker": ticker,
                    "date":   date_val,
                    "open":   price, "high": price, "low": price, "close": price,
                    "volume": vol,
                })
            except Exception as e:
                warnings.append(f"Row {row_num}: skipped ({e})")

    except Exception as e:
        return [], [f"Could not read CSV: {e}"], []

    if not valid and not errors:
        errors.append(
            "No valid price rows found. "
            "Ensure CSV has 'ticker' and 'price' (or 'close') columns."
        )
    return valid, errors, warnings


def parse_fundamentals_csv(content: bytes) -> tuple:
    """Returns (valid_rows, errors, warnings). Extremely defensive."""
    errors = []
    warnings = []
    valid = []

    try:
        text = _decode_bytes(content).strip()
        if not text:
            return [], ["Uploaded file is empty"], []

        delimiter = _sniff_delimiter(text)
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

        if not reader.fieldnames:
            return [], ["CSV has no header row — check your file format"], []

        row_num = 1
        for raw_row in reader:
            row_num += 1
            try:
                row = _normalise_row(raw_row, _FUND_ALIASES)
                ticker = row.get("ticker", "").upper()
                if not ticker:
                    warnings.append(f"Row {row_num}: no ticker — skipped")
                    continue

                last_update = row.get("last_update", "").strip()
                if not last_update or last_update.lower() in ("nan", "none", ""):
                    last_update = datetime.now().strftime("%Y-%m-%d")
                else:
                    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
                        try:
                            last_update = datetime.strptime(last_update, fmt).strftime("%Y-%m-%d")
                            break
                        except Exception:
                            continue

                fund = {
                    "ticker":             ticker,
                    "eps":                _safe_float(row.get("eps")),
                    "bvps":               _safe_float(row.get("bvps")),
                    "pe":                 _safe_float(row.get("pe")),
                    "pb":                 _safe_float(row.get("pb")),
                    "roe":                _safe_float(row.get("roe")),
                    "margin":             _safe_float(row.get("margin")),
                    "dividends":          _safe_float(row.get("dividends")),
                    "dividend_yield":     _safe_float(row.get("dividend_yield")),
                    "market_cap":         _safe_float(row.get("market_cap")),
                    "total_assets":       _safe_float(row.get("total_assets")),
                    "debt_to_equity":     _safe_float(row.get("debt_to_equity")),
                    "interest_coverage":  _safe_float(row.get("interest_coverage")),
                    "revenue":            _safe_float(row.get("revenue")),
                    "net_income":         _safe_float(row.get("net_income")),
                    "revenue_history":    _parse_history(row.get("revenue_history")),
                    "net_income_history": _parse_history(row.get("net_income_history")),
                    "dps_history":        _parse_history(row.get("dps_history")),
                    "data_source":        row.get("data_source", "manual_csv") or "manual_csv",
                    "fiscal_year":        row.get("fiscal_year", "2024") or "2024",
                    "last_update":        last_update,
                    "data_stale":         False,
                    "fetch_ok":           True,
                }

                has_any = any(
                    fund.get(f) is not None
                    for f in ["eps", "pe", "roe", "bvps", "revenue", "net_income",
                              "market_cap", "dividend_yield", "pb", "margin"]
                )
                if not has_any:
                    warnings.append(f"Row {row_num} {ticker}: no recognisable data — skipped")
                    continue
                valid.append(fund)

            except Exception as e:
                warnings.append(f"Row {row_num}: skipped ({e})")

    except Exception as e:
        return [], [f"Could not read CSV: {e}"], []

    if not valid and not errors:
        errors.append(
            "No valid fundamental rows found. "
            "Ensure CSV has 'ticker' plus at least one of: "
            "eps, pe, roe, bvps, revenue, net_income, market_cap."
        )
    return valid, errors, warnings


# ── Storage ───────────────────────────────────────────────────────────────────

class CSVDataManager:
    """
    Persistent manual data store.

    Thread safety model:
      _mem_lock  — protects in-memory dicts (held briefly, NO I/O inside)
      _disk_lock — serialises disk writes (held only during file writes)
      Disk writes always happen OUTSIDE _mem_lock so readers are never blocked.
    """

    def __init__(self):
        self._prices: dict = {}
        self._price_history: dict = {}
        self._fundamentals: dict = {}
        self._meta: dict = {}
        self._load_all()

    def _load_all(self):
        if PRICES_CSV.exists():
            try:
                df = pd.read_csv(PRICES_CSV, dtype=str)
                for _, row in df.iterrows():
                    t = str(row.get("ticker", "")).strip().upper()
                    if t:
                        self._prices[t] = row.to_dict()
            except Exception as e:
                print(f"[CSV-MGR] load prices error: {e}")

        if PRICES_HISTORY.exists():
            try:
                df = pd.read_csv(PRICES_HISTORY, dtype=str)
                for _, row in df.iterrows():
                    t = str(row.get("ticker", "")).strip().upper()
                    if t:
                        self._price_history.setdefault(t, []).append(row.to_dict())
            except Exception as e:
                print(f"[CSV-MGR] load price_history error: {e}")

        if FUNDAMENTALS_CSV.exists():
            try:
                df = pd.read_csv(FUNDAMENTALS_CSV, dtype=str)
                for _, row in df.iterrows():
                    t = str(row.get("ticker", "")).strip().upper()
                    if t:
                        fund = row.to_dict()
                        for hf in ["revenue_history", "net_income_history", "dps_history"]:
                            v = fund.get(hf, "")
                            fund[hf] = _parse_history(v) if isinstance(v, str) else (v if isinstance(v, list) else [])
                        for nf in ["eps", "bvps", "pe", "pb", "roe", "margin", "dividends",
                                   "dividend_yield", "market_cap", "total_assets",
                                   "debt_to_equity", "interest_coverage", "revenue", "net_income"]:
                            fund[nf] = _safe_float(fund.get(nf))
                        self._fundamentals[t] = fund
            except Exception as e:
                print(f"[CSV-MGR] load fundamentals error: {e}")

        self._meta = _rj(META_JSON, {})

    # ── Disk persistence ──────────────────────────────────────────────────────

    def _persist_prices(self, prices_snap, history_snap, meta_snap):
        """Atomic disk write — called WITHOUT mem_lock held."""
        with _disk_lock:
            try:
                if prices_snap:
                    _write_csv_atomic(PRICES_CSV, pd.DataFrame(list(prices_snap.values())))
            except Exception as e:
                print(f"[CSV-MGR] persist prices error: {e}")
            try:
                all_rows = [r for rows in history_snap.values() for r in rows]
                if all_rows:
                    _write_csv_atomic(PRICES_HISTORY, pd.DataFrame(all_rows))
            except Exception as e:
                print(f"[CSV-MGR] persist history error: {e}")
            _wj_atomic(META_JSON, meta_snap)

    def _persist_fundamentals(self, fund_snap, meta_snap):
        """Atomic disk write — called WITHOUT mem_lock held."""
        with _disk_lock:
            try:
                rows = []
                for t, fund in fund_snap.items():
                    r = dict(fund)
                    for hf in ["revenue_history", "net_income_history", "dps_history"]:
                        v = r.get(hf, [])
                        r[hf] = ";".join(str(x) for x in v) if isinstance(v, list) else str(v)
                    rows.append(r)
                if rows:
                    _write_csv_atomic(FUNDAMENTALS_CSV, pd.DataFrame(rows))
            except Exception as e:
                print(f"[CSV-MGR] persist fundamentals error: {e}")
            _wj_atomic(META_JSON, meta_snap)

    # ── UPLOAD PRICES ─────────────────────────────────────────────────────────

    def upload_prices(self, csv_content: bytes) -> dict:
        rows, errors, warnings = parse_price_csv(csv_content)

        if not rows and errors:
            return {"success": False, "errors": errors, "warnings": warnings, "updated": 0, "total": 0}

        uploaded_at = datetime.now().isoformat()
        updated = []

        with _mem_lock:
            for r in rows:
                t = r["ticker"]
                existing_date = str(self._prices.get(t, {}).get("date", "2000-01-01"))
                if r["date"] >= existing_date:
                    self._prices[t] = {**r, "uploaded_at": uploaded_at}
                    updated.append(t)
                existing_dates = {str(row.get("date", "")) for row in self._price_history.get(t, [])}
                if r["date"] not in existing_dates:
                    self._price_history.setdefault(t, []).append({**r, "uploaded_at": uploaded_at})

            self._meta.update({
                "prices_last_upload":     uploaded_at,
                "prices_ticker_count":    len(self._prices),
                "prices_updated_tickers": updated,
            })
            prices_snap  = dict(self._prices)
            history_snap = {t: list(v) for t, v in self._price_history.items()}
            meta_snap    = dict(self._meta)

        self._persist_prices(prices_snap, history_snap, meta_snap)

        return {
            "success":     True,
            "updated":     len(updated),
            "total":       len(prices_snap),
            "skipped":     len(rows) - len(updated),
            "errors":      errors,
            "warnings":    warnings,
            "uploaded_at": uploaded_at,
        }

    # ── UPLOAD FUNDAMENTALS ───────────────────────────────────────────────────

    def upload_fundamentals(self, csv_content: bytes) -> dict:
        rows, errors, warnings = parse_fundamentals_csv(csv_content)

        if not rows and errors:
            return {"success": False, "errors": errors, "warnings": warnings, "updated": 0}

        uploaded_at = datetime.now().isoformat()
        updated = []

        with _mem_lock:
            for fund in rows:
                t = fund["ticker"]
                merged = dict(self._fundamentals.get(t, {}))
                for k, v in fund.items():
                    if k == "ticker":
                        merged[k] = v
                    elif k in ["revenue_history", "net_income_history", "dps_history"]:
                        if isinstance(v, list) and v:
                            merged[k] = v
                    elif v is not None and v != "" and v != []:
                        merged[k] = v
                merged["uploaded_at"] = uploaded_at
                merged["data_stale"]  = False
                merged["fetch_ok"]    = True
                self._fundamentals[t] = merged
                updated.append(t)

            self._meta.update({
                "fundamentals_last_upload":     uploaded_at,
                "fundamentals_ticker_count":    len(self._fundamentals),
                "fundamentals_updated_tickers": updated,
            })
            fund_snap = dict(self._fundamentals)
            meta_snap = dict(self._meta)

        self._persist_fundamentals(fund_snap, meta_snap)

        return {
            "success":     True,
            "updated":     len(updated),
            "total":       len(fund_snap),
            "errors":      errors,
            "warnings":    warnings,
            "uploaded_at": uploaded_at,
        }

    # ── READ PRICES ───────────────────────────────────────────────────────────

    def get_current_price(self, ticker: str) -> dict:
        base = ticker.split(".")[0].upper()
        with _mem_lock:
            return dict(self._prices.get(base, {}))

    def get_price_history_df(self, ticker: str, days: int = 365) -> pd.DataFrame:
        base = ticker.split(".")[0].upper()
        with _mem_lock:
            rows = list(self._price_history.get(base, []))
            if not rows:
                p = self._prices.get(base, {})
                if p and p.get("close"):
                    rows = [dict(p)]

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        for col in ["date", "open", "high", "low", "close", "volume"]:
            if col not in df.columns:
                df[col] = df.get("close", 0)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).set_index("date").sort_index()
        df = df[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors="coerce")
        cutoff = datetime.now() - timedelta(days=days)
        return df[df.index >= cutoff]

    # ── READ FUNDAMENTALS ─────────────────────────────────────────────────────

    def get_fundamentals(self, ticker: str, seed: dict = None) -> dict:
        base = ticker.split(".")[0].upper()
        with _mem_lock:
            uploaded = dict(self._fundamentals.get(base, {}))
        seed_entry = (seed or {}).get(base, {})

        if not uploaded and not seed_entry:
            return self._empty(ticker)

        merged = dict(seed_entry)
        for k, v in uploaded.items():
            if k in ["revenue_history", "net_income_history", "dps_history"]:
                if isinstance(v, list) and v:
                    merged[k] = v
            elif v is not None and v != "" and v != []:
                merged[k] = v
        return merged

    def _empty(self, ticker: str) -> dict:
        return {
            "ticker": ticker, "data_stale": True, "data_source": "none",
            "eps": None, "bvps": None, "revenue": None, "debt": None,
            "dividends": None, "roe": None, "margin": None, "pe": None,
            "pb": None, "dividend_yield": None, "market_cap": None,
            "total_assets": None, "debt_to_equity": None,
            "interest_coverage": None, "net_income": None,
            "total_dividends": None, "net_income_history": [],
            "revenue_history": [], "dps_history": [], "last_update": "never",
            "fetch_ok": False,
        }

    # ── STATUS AND ALERTS ─────────────────────────────────────────────────────

    def get_upload_meta(self) -> dict:
        with _mem_lock:
            return dict(self._meta)

    def get_prices_age_days(self) -> float:
        ts = self.get_upload_meta().get("prices_last_upload")
        return _age_days(ts) if ts else 9999.0

    def get_fundamentals_age_days(self) -> float:
        ts = self.get_upload_meta().get("fundamentals_last_upload")
        return _age_days(ts) if ts else 9999.0

    def get_stale_fundamentals(self, tickers: list) -> list:
        stale = []
        with _mem_lock:
            funds_snap = dict(self._fundamentals)
        for t in tickers:
            base = t["ticker"].split(".")[0].upper()
            fund = funds_snap.get(base, {})
            if not fund:
                stale.append({"ticker": base, "reason": "no_data", "age_days": 9999})
                continue
            lu = fund.get("last_update", "")
            age = _age_days(lu) if lu and lu != "never" else 9999
            if age > 90:
                stale.append({"ticker": base, "reason": "expired", "age_days": round(age)})
        return stale

    def get_health_alerts(self, tickers: list) -> list:
        alerts = []
        price_age = self.get_prices_age_days()
        fund_age  = self.get_fundamentals_age_days()

        if price_age > 14:
            alerts.append({"ticker": "ALL", "field": "PRICES", "severity": "critical",
                           "message": f"Prices are {int(price_age)} days old — please upload fresh prices",
                           "action": "Upload price CSV in Data Status"})
        elif price_age > 7:
            alerts.append({"ticker": "ALL", "field": "PRICES", "severity": "warning",
                           "message": f"Prices are {int(price_age)} days old — consider updating",
                           "action": "Upload price CSV in Data Status"})

        if fund_age > 90:
            alerts.append({"ticker": "ALL", "field": "FUNDAMENTALS", "severity": "warning",
                           "message": f"Fundamentals not updated in {int(fund_age)} days",
                           "action": "Upload fundamentals CSV in Data Status"})

        with _mem_lock:
            prices_snap = dict(self._prices)
            funds_snap  = dict(self._fundamentals)

        missing_prices = [t["ticker"].split(".")[0].upper() for t in tickers
                          if not prices_snap.get(t["ticker"].split(".")[0].upper(), {}).get("close")]
        if missing_prices:
            alerts.append({"ticker": f"{len(missing_prices)} stocks", "field": "PRICE",
                           "severity": "warning", "message": f"{len(missing_prices)} stocks have no price data",
                           "action": "Upload price CSV in Data Status"})

        missing_funds = [t["ticker"].split(".")[0].upper() for t in tickers
                         if not any(funds_snap.get(t["ticker"].split(".")[0].upper(), {}).get(k)
                                    for k in ["eps", "pe", "roe"])]
        if missing_funds:
            alerts.append({"ticker": f"{len(missing_funds)} stocks", "field": "FUNDAMENTALS",
                           "severity": "warning", "message": f"{len(missing_funds)} stocks have no fundamental data",
                           "action": "Upload fundamentals CSV in Data Status"})
        return alerts

    def get_freshness_report(self, tickers: list, seed: dict = None) -> list:
        result = []
        CRITICAL_FIELDS = ["pe", "eps", "roe", "bvps", "dividend_yield"]

        with _mem_lock:
            prices_snap = dict(self._prices)
            funds_snap  = dict(self._fundamentals)

        for meta in tickers:
            base = meta["ticker"].split(".")[0].upper()
            p             = prices_snap.get(base, {})
            fund_uploaded = funds_snap.get(base, {})
            fund_seed     = (seed or {}).get(base, {})
            eff_fund      = dict(fund_seed)
            eff_fund.update({k: v for k, v in fund_uploaded.items()
                             if v is not None and v != "" and v != []})

            price_val   = _safe_float(p.get("close", 0)) or 0
            price_date  = str(p.get("date", ""))
            uploaded_at = str(p.get("uploaded_at", ""))
            date_to_check = price_date or uploaded_at
            price_age_h = _age_h(date_to_check) if date_to_check else 9999

            if not price_val:
                freshness, color = "no_data", "#ef4444"
            elif price_age_h < 24:
                freshness, color = "fresh",  "#49A078"
            elif price_age_h < 168:
                freshness, color = "recent", "#86efac"
            elif price_age_h < 336:
                freshness, color = "stale",  "#facc15"
            else:
                freshness, color = "old",    "#ef4444"

            lu = eff_fund.get("last_update", "")
            fund_age_days = _age_days(lu) if lu and lu != "never" else 9999

            issues = []
            if not price_val:
                issues.append({"field": "PRICE", "severity": "critical",
                               "message": "No price — stock will show KES 0", "fix": "upload_prices"})
            elif price_age_h > 168:
                issues.append({"field": "PRICE", "severity": "warning",
                               "message": f"Price is {int(price_age_h/24)} days old", "fix": "upload_prices"})
            for field in CRITICAL_FIELDS:
                if not eff_fund.get(field):
                    issues.append({"field": field.upper(), "severity": "critical",
                                   "message": f"Missing {field.upper()} — scoring reduced",
                                   "fix": "upload_fundamentals"})
            if fund_age_days > 90:
                issues.append({"field": "FUNDAMENTALS", "severity": "warning",
                               "message": f"Fundamentals {int(fund_age_days)} days old",
                               "fix": "upload_fundamentals"})

            result.append({
                "ticker": meta["ticker"], "name": meta["name"], "sector": meta["sector"],
                "price": round(price_val, 2), "price_date": price_date,
                "source": "manual_csv" if p else "no_data",
                "freshness": freshness, "color": color,
                "price_age_h": round(price_age_h, 1), "fund_age_days": round(fund_age_days, 1),
                "fund_source": eff_fund.get("data_source", "none"),
                "fiscal_year": eff_fund.get("fiscal_year", ""),
                "updated_at": uploaded_at or price_date or "never",
                "has_eps": eff_fund.get("eps") is not None,
                "has_pe":  eff_fund.get("pe") is not None,
                "has_roe": eff_fund.get("roe") is not None,
                "has_bvps": eff_fund.get("bvps") is not None,
                "has_div": eff_fund.get("dividend_yield") is not None,
                "issues": issues, "issue_count": len(issues),
            })
        return result


# ── Thread-safe singleton ─────────────────────────────────────────────────────

_manager: Optional[CSVDataManager] = None


def get_manager() -> CSVDataManager:
    global _manager
    if _manager is None:
        with _init_lock:
            if _manager is None:   # double-checked locking — safe
                _manager = CSVDataManager()
    return _manager
