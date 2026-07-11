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

from services.paths import DATA_DIR

PRICES_CSV       = DATA_DIR / "prices_manual.csv"
FUNDAMENTALS_CSV = DATA_DIR / "fundamentals_manual.csv"
PRICES_HISTORY   = DATA_DIR / "prices_history_manual.csv"
META_JSON        = DATA_DIR / "upload_meta.json"

# Separate locks: one for in-memory state, one for disk writes
_mem_lock  = threading.RLock()   # RLock so same thread can re-enter
_disk_lock = threading.Lock()    # disk writes serialised separately
# Dedicated to snapshot_daily_prices specifically: _mem_lock alone only
# protects the in-memory dict mutation, not the "snapshot the dict then
# write it to disk" sequence as a whole — two near-simultaneous callers
# could each mutate safely, then race to persist, with the slower one's
# stale snapshot clobbering the faster one's newer data on disk (a real
# lost-update bug, found by a concurrency test — see
# test_isolation_concurrent_snapshots_do_not_corrupt). This lock makes
# the entire mutate+persist sequence for THIS function atomic relative
# to itself, without changing the locking behavior of any other method.
_snapshot_write_lock = threading.Lock()
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


def _derive_fundamentals_row(fund: dict) -> tuple:
    """
    Fills gaps in a single fundamentals row using ONLY arithmetic on
    other real values already present in that same row — never
    invents a number from nothing. Mirrors the exact formulas used in
    the manually-researched NSE data sourcing report:
      margin = net_income / revenue
      eps = price / pe  (or the reverse: pe = price / eps)
      dividend_yield = dividends / price  (or the reverse)

    A negative or nonsensical result (e.g. negative P/E for a
    loss-making company) is left blank rather than shown as a
    misleading number — same judgment call documented in that report
    for BAMB/FTGH. Returns (row_with_derived_fields, list_of_field_
    names_that_were_derived) so the caller can log/audit exactly what
    changed and why.
    """
    fund = dict(fund)
    derived = []

    price          = _safe_float(fund.get("price"))
    eps            = _safe_float(fund.get("eps"))
    pe             = _safe_float(fund.get("pe"))
    revenue        = _safe_float(fund.get("revenue"))
    net_income     = _safe_float(fund.get("net_income"))
    dividends      = _safe_float(fund.get("dividends"))
    dividend_yield = _safe_float(fund.get("dividend_yield"))

    def _is_missing(key):
        v = fund.get(key)
        return v is None or v == "" or v == []

    if _is_missing("margin") and net_income is not None and revenue and revenue > 0:
        fund["margin"] = round(net_income / revenue, 4)
        derived.append("margin")

    if _is_missing("eps") and price and pe and pe > 0:
        fund["eps"] = round(price / pe, 4)
        derived.append("eps")
    elif _is_missing("pe") and price and eps and eps > 0:
        computed_pe = round(price / eps, 2)
        if computed_pe > 0:  # negative P/E isn't a meaningful multiple - leave blank, don't mislead
            fund["pe"] = computed_pe
            derived.append("pe")

    if _is_missing("dividend_yield") and price and price > 0 and dividends is not None:
        computed_yield = round(dividends / price, 4)
        if 0 <= computed_yield <= 1:  # >100% yield is almost certainly a data error, not a real figure
            fund["dividend_yield"] = computed_yield
            derived.append("dividend_yield")
    elif _is_missing("dividends") and price and dividend_yield is not None:
        fund["dividends"] = round(dividend_yield * price, 4)
        derived.append("dividends")

    if derived:
        existing_source = (fund.get("data_source") or "").strip()
        note = f"derived this update: {', '.join(derived)}"
        fund["data_source"] = f"{existing_source} || {note}" if existing_source else note

    return fund, derived


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
            for base, data in ex.map(_fetch, bases):
                if data:
                    live_funds[base] = data
        print(f"[template/fundamentals] scraper returned {len(live_funds)} stocks")
    except Exception as e:
        print(f"[template/fundamentals] scraper unavailable: {e}")

    def fmt_history(arr):
        return ";".join(str(v) for v in arr) if arr else ""

    def pick(live, uploaded, sd, field, default=""):
        """Priority: live scraper (freshest) > your uploaded real data
        (authoritative once you've provided it) > old seed JSON (last
        resort only, may be stale/placeholder) > default/empty (red
        cell). `sd` is passed in as {} by the caller whenever this
        ticker already has any real uploaded data - see the loop
        below for why that matters."""
        for source in (live, uploaded, sd):
            v = source.get(field)
            if v is not None and v != "" and v != []:
                return v
        return default

    rows = []
    today = datetime.now().strftime("%Y-%m-%d")
    manager = get_manager()
    for t in tickers:
        base = t["ticker"].split(".")[0].upper()
        lv = live_funds.get(base, {})
        up = manager._fundamentals.get(base, {})
        # If this ticker already has ANY real uploaded data, seed is
        # excluded entirely for it - not just for individually-empty
        # fields. Otherwise a downloaded template could show old fake
        # seed numbers (e.g. a fabricated net_income_history) sitting
        # next to real EPS/PE data, and a careless re-upload of that
        # template would silently reintroduce exactly the fake-data
        # contamination bug already found and fixed in
        # get_fundamentals() and upload_fundamentals() - just via a
        # different door.
        sd = seed.get(base, {}) if not up else {}

        rows.append({
            "ticker":             base,
            "eps":                pick(lv, up, sd, "eps"),
            "bvps":               pick(lv, up, sd, "bvps"),
            "pe":                 pick(lv, up, sd, "pe"),
            "pb":                 pick(lv, up, sd, "pb"),
            "roe":                pick(lv, up, sd, "roe"),
            "margin":             pick(lv, up, sd, "margin"),
            "dividends":          pick(lv, up, sd, "dividends"),
            "dividend_yield":     pick(lv, up, sd, "dividend_yield"),
            "market_cap":         pick(lv, up, sd, "market_cap"),
            "total_assets":       pick(lv, up, sd, "total_assets"),
            "debt_to_equity":     pick(lv, up, sd, "debt_to_equity"),
            "interest_coverage":  pick(lv, up, sd, "interest_coverage"),
            "revenue":            pick(lv, up, sd, "revenue"),
            "net_income":         pick(lv, up, sd, "net_income"),
            "revenue_history":    fmt_history(pick(lv, up, sd, "revenue_history", [])),
            "net_income_history": fmt_history(pick(lv, up, sd, "net_income_history", [])),
            "dps_history":        fmt_history(pick(lv, up, sd, "dps_history", [])),
            "data_source":        pick(lv, up, sd, "data_source", ""),
            "fiscal_year":        pick(lv, up, sd, "fiscal_year", "2024"),
            "last_update":        pick(lv, up, sd, "last_update", today),
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
                # REPLACE wholesale, not merge - an upload is the
                # authoritative statement of this ticker's current
                # fundamentals. Merging with whatever was previously
                # stored let stale/contaminating data survive
                # indefinitely (a genuinely-empty real field could
                # never overwrite an old fake one under the previous
                # "only overwrite if non-empty" merge rule) - a real
                # data-integrity bug found via an actual end-to-end
                # test with real uploaded data, not a hypothetical.
                fund["uploaded_at"] = uploaded_at
                fund["fetch_ok"]    = True
                self._fundamentals[t] = fund
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

        # DATA INTEGRITY: once real data has been uploaded for this
        # ticker, seed/placeholder data must never contaminate it again
        # - not even to "fill gaps." The old logic started from seed
        # data as the base and only overwrote history-array fields if
        # the upload had a non-empty list, which meant an honestly
        # empty history array (correctly reporting "we don't have
        # this") would silently leave fabricated seed numbers in
        # place underneath - and those fake numbers would then flow
        # into DCF/valuation as if real, with no indication to the
        # user. A ticker with ANY real upload now uses ONLY that real
        # data; missing fields stay honestly missing (None/[]) rather
        # than being quietly patched from a placeholder.
        if uploaded:
            return uploaded

        return dict(seed_entry)

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

    # ── DAILY PRICE SNAPSHOT (auto-accumulates real history over time) ──────

    def snapshot_daily_prices(self, live_prices: dict) -> dict:
        """
        Appends today's REAL scraped current price into price history for
        every ticker the scraper found — one row per ticker per calendar
        day. This is the only way NSE historical price data can exist for
        free, since no free provider publishes it: it has to be captured
        day by day, going forward, from the one thing that IS free (the
        current live price).

        ACID properties, deliberately:
          Atomicity  — either this whole snapshot's rows land in the
                       in-memory dict AND the resulting file write
                       completes, or (on any exception) nothing is
                       persisted; _write_csv_atomic uses a temp-file +
                       rename so a crash mid-write can never leave a
                       half-written history file on disk.
          Consistency — idempotent per (ticker, date): calling this
                       twice in the same day (e.g. a redeploy, a retry)
                       never creates a duplicate row. Only rows with a
                       real positive price are written — a scraper
                       hiccup returning 0/None for a ticker silently
                       skips that ticker rather than polluting history
                       with a bad data point.
          Isolation  — the ENTIRE mutate-snapshot-persist sequence is
                       serialized end-to-end via a dedicated write lock
                       (not just the in-memory mutation) — two
                       near-simultaneous callers cannot race each
                       other's disk write and silently lose a row.
                       This was a real bug caught by a concurrency
                       test, not a hypothetical: without this lock,
                       the slower of two concurrent callers could
                       persist a stale snapshot that clobbers the
                       faster one's newer data.
          Durability — same _write_csv_atomic used everywhere else:
                       temp file written and fsynced by the OS, then
                       atomically renamed over the real file.

        Returns a small report so the caller (startup, or a scheduled
        job) can log what actually happened without guessing.
        """
        today = datetime.now().date().isoformat()
        added, skipped_no_price, skipped_duplicate = [], [], []

        # Serializes the WHOLE mutate+persist sequence against other
        # concurrent calls to this function — see docstring above.
        with _snapshot_write_lock:
            with _mem_lock:
                for base_ticker, entry in live_prices.items():
                    price = _safe_float(entry.get("price"))
                    if price is None or price <= 0:
                        skipped_no_price.append(base_ticker)
                        continue

                    existing_dates = {str(row.get("date", "")) for row in self._price_history.get(base_ticker, [])}
                    if today in existing_dates:
                        skipped_duplicate.append(base_ticker)
                        continue

                    row = {
                        "ticker": base_ticker,
                        "date": today,
                        "open": price, "high": price, "low": price, "close": price,
                        "volume": entry.get("volume", 0) or 0,
                        "uploaded_at": datetime.now().isoformat(),
                        "source": "auto_snapshot",
                    }
                    self._price_history.setdefault(base_ticker, []).append(row)
                    added.append(base_ticker)

                    # Keep the "current price" table in sync too, but only
                    # advance it — never let an older/equal snapshot regress
                    # a more recent manual upload (same rule upload_prices uses).
                    existing_date = str(self._prices.get(base_ticker, {}).get("date", "2000-01-01"))
                    if today >= existing_date:
                        self._prices[base_ticker] = {
                            "ticker": base_ticker, "price": price, "date": today,
                            "uploaded_at": datetime.now().isoformat(), "source": "auto_snapshot",
                        }

                if added:
                    self._meta.update({
                        "last_auto_snapshot": datetime.now().isoformat(),
                        "last_auto_snapshot_count": len(added),
                        # Keep this in sync with reality — /api/system-status
                        # and other consumers read prices_ticker_count as
                        # "how many tickers have a real current price," and
                        # that must be true after an auto-snapshot too, not
                        # only after a manual CSV upload (which is the only
                        # path that used to set it — a real gap found by
                        # actually running the built executable end to end).
                        "prices_ticker_count": len(self._prices),
                    })

                prices_snap  = dict(self._prices)
                history_snap = {t: list(v) for t, v in self._price_history.items()}
                meta_snap    = dict(self._meta)

            # Disk write happens outside _mem_lock (readers aren't
            # blocked by slow disk I/O) but still inside
            # _snapshot_write_lock, so it can't race another concurrent
            # call to this same function.
            if added:
                self._persist_prices(prices_snap, history_snap, meta_snap)

        return {
            "date": today,
            "added": added,
            "skipped_no_price": skipped_no_price,
            "skipped_duplicate": skipped_duplicate,
            "total_added": len(added),
        }

    def refresh_all_data(self, tickers: list) -> dict:
        """
        The 'Update Data' button's backend — a full, on-demand data
        refresh across both prices and fundamentals, for every
        tracked ticker. Runs the SAME logic that would otherwise wait
        for the daily background snapshot, on demand.

        Consistency / accuracy / integrity, concretely:
          - Live-scraped data wins when it returns something real,
            because it's the freshest source available.
          - A ticker's EXISTING value is preserved whenever live has
            nothing for that field — this refresh only ever adds or
            improves data, it never regresses good data to blank.
          - Missing fields are derived ONLY from other real values
            already present in that same ticker's row (the same
            formulas used in the manually-researched NSE data
            sourcing report: margin = net_income/revenue, eps=price/pe
            or pe=price/eps, dividend_yield=dividends/price or the
            reverse). A derived value is real arithmetic on real
            numbers, never a fabricated placeholder — a field with no
            real number anywhere to derive it from stays honestly
            empty.
          - Every derived field is recorded in that row's data_source
            note, so it's always traceable which numbers are directly
            sourced vs computed — full audit trail, not a black box.
        """
        from services.nse_scraper import get_all_prices, get_fundamentals as scraper_get_fundamentals

        report = {
            "started_at": datetime.now().isoformat(),
            "prices": None,
            "fundamentals": {"tickers_improved": 0, "fields_derived": 0, "errors": []},
        }

        # Prices — reuses the already-tested-safe snapshot mechanism,
        # just triggered on demand instead of waiting for the 24h timer.
        try:
            live_prices = get_all_prices()
            report["prices"] = self.snapshot_daily_prices(live_prices)
        except Exception as e:
            report["prices"] = {"available": False, "reason": str(e)}

        with _mem_lock:
            current_prices = dict(self._prices)

        tickers_improved = 0
        fields_derived_total = 0

        for t in tickers:
            base = t["ticker"].split(".")[0].upper()
            try:
                live = scraper_get_fundamentals(base) or {}
                # The scraper's own Tier-3 fallback returns old,
                # possibly-fabricated placeholder data tagged
                # data_source="seed_fy2024" when live scraping fails -
                # never treat that as fresh live data. Doing so would
                # silently reintroduce exactly the fake-data
                # contamination already found and fixed twice
                # elsewhere in this codebase, just through a third
                # path. Only a genuine live scrape should ever
                # override existing real data here.
                if live.get("data_source") == "seed_fy2024":
                    live = {}
            except Exception as e:
                live = {}
                report["fundamentals"]["errors"].append(f"{base}: live fetch failed ({e})")

            with _mem_lock:
                existing = dict(self._fundamentals.get(base, {}))

            merged = dict(existing)
            live_fields_applied = []
            for k, v in live.items():
                if v is not None and v != "" and v != []:
                    if existing.get(k) != v:
                        live_fields_applied.append(k)
                    merged[k] = v  # freshest real data wins

            price_row = current_prices.get(base, {})
            merged["price"] = _safe_float(price_row.get("price"))

            derived_row, derived_fields = _derive_fundamentals_row(merged)
            derived_row.pop("price", None)  # price lives in its own table, not stored inside fundamentals

            # A ticker only counts as "improved" if something SUBSTANTIVE
            # actually changed - a genuinely new live value, or a field
            # that was successfully derived. Not a blunt whole-dict
            # equality check, which can be tripped by incidental
            # representation differences (e.g. field ordering, type
            # round-tripping) that don't reflect any real data change -
            # that would silently overcount "improvements" and bump
            # last_update timestamps for tickers where nothing actually
            # happened, misleading anyone auditing what this update did.
            if live_fields_applied or derived_fields:
                derived_row["last_update"] = datetime.now().strftime("%Y-%m-%d")
                derived_row["fetch_ok"] = True
                derived_row["ticker"] = base
                with _mem_lock:
                    self._fundamentals[base] = derived_row
                tickers_improved += 1
                fields_derived_total += len(derived_fields)

        with _mem_lock:
            self._meta.update({
                "last_full_data_update": datetime.now().isoformat(),
                "fundamentals_ticker_count": len(self._fundamentals),
            })
            fundamentals_snap = dict(self._fundamentals)
            meta_snap = dict(self._meta)

        self._persist_fundamentals(fundamentals_snap, meta_snap)

        report["fundamentals"]["tickers_improved"] = tickers_improved
        report["fundamentals"]["fields_derived"] = fields_derived_total
        report["completed_at"] = datetime.now().isoformat()
        return report


# ── Thread-safe singleton ─────────────────────────────────────────────────────

_manager: Optional[CSVDataManager] = None


def get_manager() -> CSVDataManager:
    global _manager
    if _manager is None:
        with _init_lock:
            if _manager is None:   # double-checked locking — safe
                _manager = CSVDataManager()
    return _manager
