"""
csv_data_manager.py — the data layer: your CSV uploads plus the "Update Data" refresh.
Uploaded / researched data is authoritative; live sources only fill gaps and re-price ratios.

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
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from services.paths import DATA_DIR
from services.nse_scraper import last_trading_day, market_clock

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


def _price_is_fresh_today(entry: dict, today: str, require_ts: bool = True) -> bool:
    """True for a price actually fetched today. Placeholder ("manual_stub")
    and older cached prices are not fresh. With require_ts=False an entry
    that carries no timestamp at all is given the benefit of the doubt (used
    when recording prices handed in directly)."""
    if not entry or entry.get("source") == "manual_stub" or entry.get("stale") is True:
        return False
    ts = str(entry.get("updated_at") or "")
    if ts == "manual":
        return False
    if not ts:
        return not require_ts
    try:
        return datetime.fromisoformat(ts).date().isoformat() == today
    except ValueError:
        return False


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


_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y",
                 "%d-%b-%Y", "%d %b %Y", "%b %d, %Y", "%d/%m/%y")


def _parse_date(text: str) -> Optional[str]:
    """ISO date string, or None when the text is not a recognised date.
    (The previous loop overwrote the value with today's date after the first
    failed format, so every non-ISO date silently became today.)"""
    text = str(text).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _price_of(entry) -> Optional[float]:
    """Current price of a stored price entry. Entries come from CSV uploads
    ("close") and from live snapshots ("price"); readers must accept both."""
    if not entry:
        return None
    for key in ("close", "price"):
        v = _safe_float(entry.get(key))
        if v is not None and v > 0:
            return v
    return None


def audit_fundamentals_row(row: dict, price: Optional[float]) -> list:
    """Internal-consistency problems in one stock's fundamentals (empty list = clean).
    Pure arithmetic on values already present - nothing is looked up or guessed."""
    issues = []
    eps, pe = _safe_float(row.get("eps")), _safe_float(row.get("pe"))
    div, dy = _safe_float(row.get("dividends")), _safe_float(row.get("dividend_yield"))
    if pe and pe > 0 and eps is not None and eps <= 0:
        issues.append("P/E is set but EPS is not positive")
    if row.get("check"):
        issues.append(str(row["check"]))      # set by _reprice_all; stays until new data replaces the row
    elif price and eps and eps > 0 and pe and pe > 0:
        implied = price / eps
        if abs(pe - implied) / implied > 0.15:
            issues.append(f"P/E {pe:g} disagrees with price ÷ EPS ({implied:.1f})")
    if dy is not None and 0.25 < dy <= _FRACTION_FIELDS["dividend_yield"]:
        issues.append(f"dividend yield {dy:.0%} is unusually high — check for a one-off special dividend")
    if eps and eps > 0 and div and div > 1.5 * eps:
        issues.append(f"dividend {div:g} is over 150% of EPS {eps:g}")
    for field, ceiling in _FRACTION_FIELDS.items():
        v = _safe_float(row.get(field))
        if v is not None and v > ceiling:
            issues.append(f"{field} {v:g} looks like a percentage, expected a fraction")
    lu = _parse_date(str(row.get("last_update") or ""))
    if lu and lu > date.today().isoformat():
        issues.append(f"last_update {lu} is in the future")
    return issues


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
    """Price template. A cell is pre-filled ONLY with a price fetched today from
    a live source; everything else is left empty for you to fill (stale or
    placeholder numbers must never look like current prices)."""
    live_prices = {}
    try:
        from services.nse_scraper import get_all_prices
        live_prices = get_all_prices()
    except Exception as e:
        print(f"[template/prices] scraper unavailable: {e}")
    today = datetime.now().strftime("%Y-%m-%d")

    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=PRICE_FIELDS)
    w.writeheader()
    for t in tickers:
        base = t["ticker"].split(".")[0].upper()
        entry = live_prices.get(base, {})
        price = entry.get("price") if _price_is_fresh_today(entry, today) else None
        w.writerow({"ticker": base, "price": price if price else ""})
    return out.getvalue()


def generate_fundamentals_template(tickers: list, seed: dict, uploaded: Optional[dict] = None) -> str:
    """Fundamentals template, pre-filled from data already on file:
    your uploaded data first, the seed JSON only for tickers with no upload at
    all (mixing the two would reintroduce placeholder numbers next to real ones).
    No network calls - the download is instant even when every live source is down."""
    uploaded = uploaded if uploaded is not None else get_manager().get_all_fundamentals()

    def fmt_history(arr):
        return ";".join(str(v) for v in arr) if arr else ""

    rows = []
    for t in tickers:
        base = t["ticker"].split(".")[0].upper()
        src = uploaded.get(base) or seed.get(base, {})

        def v(field, default=""):
            x = src.get(field)
            return default if x is None or x == "" or x == [] else x

        rows.append({
            "ticker": base,
            **{f: v(f) for f in ("eps", "bvps", "pe", "pb", "roe", "margin", "dividends",
                                 "dividend_yield", "market_cap", "total_assets",
                                 "debt_to_equity", "interest_coverage", "revenue", "net_income")},
            **{f: fmt_history(v(f, [])) for f in ("revenue_history", "net_income_history", "dps_history")},
            "data_source": v("data_source"),
            "fiscal_year": v("fiscal_year", ""),
            "last_update": v("last_update"),   # blank stays blank: the parser dates it on upload
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

                raw_date = (row.get("date") or row.get("last_update") or "").strip()
                if raw_date and raw_date.lower() not in ("nan", "none"):
                    date_val = _parse_date(raw_date)
                    if date_val is None:
                        warnings.append(f"{ticker} row {row_num}: unrecognised date '{raw_date}' — skipped")
                        continue
                    if date_val > (date.today() + timedelta(days=1)).isoformat():
                        warnings.append(f"{ticker} row {row_num}: date {date_val} is in the future — skipped")
                        continue
                else:
                    date_val = today

                vol = int(_safe_float(row.get("volume", "0")) or 0)
                valid.append({
                    "ticker": ticker,
                    "date":   date_val,
                    "open":   price, "high": price, "low": price, "close": price,
                    "price":  price,
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


# Fraction fields (0.2 = 20%) and the largest value that is still believable as a fraction.
# Above it the number can only be a percentage typed as a fraction (a yield or margin over 100%
# is impossible; ROE over 150% does not occur on the NSE).
_FRACTION_FIELDS = {"dividend_yield": 1.0, "margin": 1.0, "roe": 1.5}


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

                raw_update = row.get("last_update", "").strip()
                last_update = _parse_date(raw_update) if raw_update.lower() not in ("", "nan", "none") else None
                if raw_update and raw_update.lower() not in ("nan", "none") and last_update is None:
                    warnings.append(f"{ticker} row {row_num}: unrecognised last_update '{raw_update}' — "
                                    "using today (the upload date)")
                last_update = last_update or datetime.now().strftime("%Y-%m-%d")

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
                    "fiscal_year":        row.get("fiscal_year", "") or "",
                    "last_update":        last_update,
                    "data_stale":         False,
                    "fetch_ok":           True,
                }

                for field, ceiling in _FRACTION_FIELDS.items():
                    v = fund.get(field)
                    if v is not None and v > ceiling:
                        warnings.append(f"{ticker}: {field} {v:g} looks like a percentage — "
                                        f"stored as {v / 100:g} (these fields are fractions, 0.2 = 20%)")
                        fund[field] = v / 100

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

_PASTE_LINE = re.compile(r"\s*([A-Za-z&]{2,7})[\s,;:=]+(?:KSh|KES)?\s?(\d[\d,]*(?:\.\d+)?)\s*")
_PASTE_KSH = re.compile(r"KSh\s?(\d[\d,]*(?:\.\d+)?)")


def parse_pasted_prices(text: str, known: set) -> tuple:
    """Prices from text the user copied out of a website. Two shapes are understood:
      A) one stock per line:   SCOM 36.40   /   SCOM,36.40   /   SCOM<tab>36.40
      B) a table copied whole: each known ticker, then the FIRST 'KSh<price>' after it
         (the ticker may be glued to the company name, e.g. 'Safaricom PlcSCOM').
    Only tickers in `known` count and only 'KSh' prices in shape B, so index levels, market
    caps and page chrome cannot be picked up by accident. A ticker seen with two different
    prices is a conflict and is dropped, never guessed.
    Returns ({ticker: price}, [conflicting tickers])."""
    seen: dict = {}

    def put(raw_ticker, raw_price):
        t = raw_ticker.upper()
        t = {"HFCB": "HFCK"}.get(t, t)
        if t not in known:
            return
        try:
            price = float(raw_price.replace(",", ""))
        except ValueError:
            return
        if 0.1 < price < 100000:
            seen.setdefault(t, []).append(price)

    for line in text.splitlines():
        m = _PASTE_LINE.fullmatch(line)
        if m:
            put(m.group(1), m.group(2))

    flat = re.sub(r"\s+", " ", text)
    names = sorted(known | {"HFCB"}, key=len, reverse=True)
    alt = "|".join(map(re.escape, names))
    # a ticker stands alone, OR is glued to an upper-case name ("...ETFGLD") but then must be
    # followed directly by its KSh price
    marks = list(re.finditer(rf"(?<![A-Z&])({alt})(?![A-Z&])|({alt})(?= ?KSh\d)", flat))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(flat)
        pm = _PASTE_KSH.search(flat[m.end():end][:150])
        if pm:
            put(m.group(1) or m.group(2), pm.group(1))

    prices, conflicts = {}, []
    for t, vals in seen.items():
        if max(vals) - min(vals) > 0.005 * min(vals):
            conflicts.append(t)
        else:
            prices[t] = vals[0]
    return prices, sorted(conflicts)


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
            old_prices = dict(self._prices)
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
        self._reprice_all(old_prices)

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
        self._reprice_all()

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

    def import_pasted_prices(self, text: str, known: set, confirm: bool = False,
                             accept_suspect: bool = False) -> dict:
        """Two steps so nothing is saved blind: confirm=False returns a preview (price, last
        recorded close, % change, ok/suspect per stock); confirm=True saves exactly what the
        preview showed. 'suspect' = a move NSE's daily limit cannot explain (likely a
        mis-paste); those are saved only with accept_suspect=True."""
        prices, conflicts = parse_pasted_prices(text, known)
        trade_date = last_trading_day()
        rows = []
        for t in sorted(prices):
            price = prices[t]
            with _mem_lock:
                hist = [r for r in self._price_history.get(t, []) if _safe_float(r.get("close"))]
            prev = max(hist, key=lambda r: str(r["date"])) if hist else None
            status, change = "ok", None
            if prev:
                prev_close = _safe_float(prev["close"])
                change = round((price / prev_close - 1) * 100, 2)
                gap = (trade_date - date.fromisoformat(str(prev["date"])[:10])).days
                if not self._plausible(price, prev_close, gap):
                    status = "suspect"
            rows.append({"ticker": t, "price": price, "previous": prev and _safe_float(prev["close"]),
                         "previous_date": prev and str(prev["date"])[:10], "change_pct": change, "status": status})
        out = {"date": trade_date.isoformat(), "rows": rows, "conflicts": conflicts, "saved": False}
        if not confirm:
            return out
        to_save = [r for r in rows if r["status"] == "ok" or accept_suspect]
        if not to_save:
            out["error"] = "Nothing to save - no recognised prices (or all were held back as suspect)."
            return out
        csv_text = "ticker,date,price\n" + "".join(f"{r['ticker']},{out['date']},{r['price']}\n" for r in to_save)
        res = self.upload_prices(csv_text.encode())
        out.update(saved=bool(res.get("success")), saved_count=len(to_save), upload=res)
        return out

    def get_price_history_df(self, ticker: str, days: int = 365) -> pd.DataFrame:
        base = ticker.split(".")[0].upper()
        with _mem_lock:
            rows = list(self._price_history.get(base, []))
            if not rows:
                p = self._prices.get(base, {})
                if _price_of(p):
                    rows = [{**p, "close": _price_of(p)}]

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

    def get_all_fundamentals(self) -> dict:
        """Copy of every stored fundamentals row (public alternative to touching _fundamentals)."""
        with _mem_lock:
            return {t: dict(f) for t, f in self._fundamentals.items()}

    def get_upload_meta(self) -> dict:
        with _mem_lock:
            return dict(self._meta)

    def get_prices_age_days(self) -> float:
        """Age of the newest price write - a manual upload OR a live snapshot
        (previously only uploads counted, so a successful update still showed "Outdated")."""
        meta = self.get_upload_meta()
        ages = [_age_days(meta[k]) for k in ("prices_last_upload", "last_auto_snapshot") if meta.get(k)]
        return min(ages) if ages else 9999.0

    def get_fundamentals_age_days(self) -> float:
        ts = self.get_upload_meta().get("fundamentals_last_upload")
        return _age_days(ts) if ts else 9999.0

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

        by_issue: dict = {}
        for t in tickers:
            base = t["ticker"].split(".")[0].upper()
            if base in funds_snap:
                for issue in audit_fundamentals_row(funds_snap[base], _price_of(prices_snap.get(base))):
                    by_issue.setdefault(re.sub(r"[\d.,%]+", "#", issue), []).append(f"{base}: {issue}")
        for _kind, items in sorted(by_issue.items(), key=lambda kv: -len(kv[1]))[:5]:
            shown = "; ".join(items[:3]) + (f" … (+{len(items) - 3} more)" if len(items) > 3 else "")
            alerts.append({"ticker": f"{len(items)} stocks", "field": "DATA CHECK", "severity": "warning",
                           "message": shown, "action": "Verify these figures, then correct via Data Status"})

        missing_prices = [t["ticker"].split(".")[0].upper() for t in tickers
                          if not _price_of(prices_snap.get(t["ticker"].split(".")[0].upper()))]
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

    def get_freshness_report(self, tickers: list, seed: dict = None, overrides: dict = None) -> list:
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
            # Same precedence as get_fundamentals(): once a ticker has uploaded
            # data, seed values never fill gaps (the old report said "has EPS"
            # from seed while scoring saw None). Manual single-field entries win.
            eff_fund = dict(fund_uploaded if fund_uploaded else fund_seed)
            eff_fund.update((overrides or {}).get(base, {}))

            price_val   = _price_of(p) or 0
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

    @staticmethod
    def _plausible(price: float, prev_close: float, gap_days: int) -> bool:
        """NSE limits a stock to about +/-10% a day. A move far beyond what the elapsed
        trading days allow is more likely a bad scrape (or an unapplied split/bonus) than
        a real price - it is held back and reported instead of being written to history.
        Not applied after a long gap (nothing reliable to compare with)."""
        if prev_close <= 0 or gap_days > 30:
            return True
        trading_days = max(1, -(-gap_days * 5 // 7))
        return abs(price / prev_close - 1) <= min(0.60, 0.10 * trading_days + 0.05)

    def snapshot_daily_prices(self, live_prices: dict, provisional: bool = False) -> dict:
        """
        Records the real live price into price history: one row per ticker per
        trading day. This is how NSE history accumulates for free - no free
        provider publishes it, so it is captured day by day.

        Guarantees (each covered by tests):
          Atomicity   - rows land in memory and on disk together; files are
                        written temp-file + rename, never half-written.
          Consistency - only real positive prices fetched TODAY are written (stubs /
                        old cache are skipped). The row is dated with the trade date
                        of the Nairobi market session (a weekend run records Friday,
                        a pre-market run records yesterday's close as yesterday) or the
                        quote's own date when the source states one. An implausible
                        jump versus the last close is held back (skipped_suspect).
                        One row per (ticker, day): the first FINAL price wins.
          Provisional - during market hours the price is not the close yet. With
                        provisional=True the row is marked auto_snapshot_live and is
                        replaced by the next snapshot of that day (the final one then
                        locks it). Manually uploaded rows are never replaced.
          Isolation   - mutate+persist is serialised end to end.
          Durability  - atomic rename over the real file.
        """
        today = datetime.now().date().isoformat()          # freshness check
        trade_date = last_trading_day().isoformat()
        added, updated = [], []
        skipped_no_price, skipped_duplicate, skipped_stale, skipped_suspect = [], [], [], []
        source_tag = "auto_snapshot_live" if provisional else "auto_snapshot"

        with _snapshot_write_lock:
            with _mem_lock:
                old_prices = dict(self._prices)
                for base_ticker, entry in live_prices.items():
                    price = _safe_float(entry.get("price"))
                    if price is None or price <= 0:
                        skipped_no_price.append(base_ticker)
                        continue
                    if not _price_is_fresh_today(entry, today, require_ts=False):
                        skipped_stale.append(base_ticker)
                        continue

                    row_date = str(entry.get("price_date") or trade_date)[:10]
                    if row_date > trade_date:
                        row_date = trade_date
                    history = self._price_history.setdefault(base_ticker, [])
                    existing = next((r for r in history if str(r.get("date", "")) == row_date), None)
                    if existing is not None and existing.get("source") != "auto_snapshot_live":
                        skipped_duplicate.append(base_ticker)
                        continue

                    earlier = [r for r in history if str(r.get("date", "")) < row_date
                               and _safe_float(r.get("close"))]
                    if earlier:
                        prev = max(earlier, key=lambda r: str(r["date"]))
                        gap = (date.fromisoformat(row_date) - date.fromisoformat(str(prev["date"])[:10])).days
                        if not self._plausible(price, _safe_float(prev["close"]), gap):
                            skipped_suspect.append(f"{base_ticker} ({prev['close']} -> {price})")
                            continue

                    now_iso = datetime.now().isoformat()
                    fields = {"open": price, "high": price, "low": price, "close": price, "price": price,
                              "volume": entry.get("volume", 0) or 0, "uploaded_at": now_iso, "source": source_tag}
                    if existing is not None:
                        existing.update(fields)
                        row = existing
                        updated.append(base_ticker)
                    else:
                        row = {"ticker": base_ticker, "date": row_date, **fields}
                        history.append(row)
                        added.append(base_ticker)

                    # Keep the "current price" table in sync, but only ever advance it.
                    if row_date >= str(self._prices.get(base_ticker, {}).get("date", "2000-01-01")):
                        self._prices[base_ticker] = dict(row)

                changed = added or updated
                if changed:
                    self._meta.update({
                        "last_auto_snapshot": datetime.now().isoformat(),
                        "last_auto_snapshot_count": len(changed),
                        "prices_ticker_count": len(self._prices),
                    })
                prices_snap  = dict(self._prices)
                history_snap = {t: list(v) for t, v in self._price_history.items()}
                meta_snap    = dict(self._meta)

            if changed:
                self._persist_prices(prices_snap, history_snap, meta_snap)

        if changed:
            self._reprice_all(old_prices)

        return {
            "date": trade_date,
            "provisional": provisional,
            "added": added,
            "updated": updated,
            "skipped_no_price": skipped_no_price,
            "skipped_duplicate": skipped_duplicate,
            "skipped_stale": skipped_stale,
            "skipped_suspect": skipped_suspect,
            "total_added": len(added) + len(updated),
        }

    def final_snapshot_done(self, trade_date: str) -> bool:
        return self.get_upload_meta().get("last_final_snapshot_date") == trade_date

    def mark_final_snapshot(self, trade_date: str):
        with _mem_lock:
            self._meta["last_final_snapshot_date"] = trade_date
            meta_snap = dict(self._meta)
        with _disk_lock:
            _wj_atomic(META_JSON, meta_snap)

    # Price-driven ratios: recomputed from the fresh price and the SAME stored
    # EPS / dividend, so they always agree with the researched numbers.
    @staticmethod
    def _source_with(existing: str, notes: list) -> str:
        """data_source trail: keeps the original source and one-off notes (e.g. 'live ... filled: eps'),
        replaces any earlier 'repriced ...' note so the string cannot grow with every price change."""
        parts = [p.strip() for p in (existing or "").split(" || ")
                 if p.strip() and not p.strip().startswith("repriced ")]
        parts += [n for n in notes if n not in parts]
        return " || ".join(parts)

    def _reprice_all(self, old_prices: Optional[dict] = None) -> int:
        """P/E, dividend yield and P/B always reflect the CURRENT price. Called after every
        price or fundamentals write (CSV, paste, manual, live snapshot), so ratios can never
        be left at an old price. Uses only EPS / DPS / BVPS already stored; returns the number
        of stocks changed. last_update is untouched - re-pricing does not make EPS newer.

        Quarantine: if a row's stored P/E did not match price ÷ EPS at the price it was written
        against (old_prices), one of the two is wrong. Re-pricing would overwrite the P/E from a
        suspect EPS and make the problem invisible, so that row is flagged (row["check"]) and
        left alone until you verify it and upload corrected data."""
        today = datetime.now().strftime("%Y-%m-%d")
        changed_n = 0
        with _snapshot_write_lock:
            with _mem_lock:
                for base, row in self._fundamentals.items():
                    price = _price_of(self._prices.get(base))
                    if not price or row.get("check"):
                        continue
                    new = dict(row)
                    old = _price_of((old_prices or {}).get(base))
                    eps_, pe_ = _safe_float(row.get("eps")), _safe_float(row.get("pe"))
                    if old and eps_ and eps_ > 0 and pe_ and pe_ > 0 and abs(pe_ - old / eps_) / (old / eps_) > 0.15:
                        new["check"] = (f"P/E {pe_:g} disagrees with price ÷ EPS ({old / eps_:.1f}) — "
                                        "verify EPS; ratios are not auto-repriced for this stock")
                        self._fundamentals[base] = new
                        changed_n += 1
                        continue
                    changed = self._reprice(new, price, today)
                    if changed:
                        new["data_source"] = self._source_with(
                            row.get("data_source"), [f"repriced {today} from current price: {', '.join(changed)}"])
                        self._fundamentals[base] = new
                        changed_n += 1
                if changed_n:
                    funds_snap, meta_snap = dict(self._fundamentals), dict(self._meta)
            if changed_n:
                self._persist_fundamentals(funds_snap, meta_snap)
        return changed_n

    def _reprice(self, row: dict, price, today: str) -> list:
        changed = []
        if not price or price <= 0:
            return changed
        eps = _safe_float(row.get("eps"))
        if eps and eps > 0:
            pe = round(price / eps, 2)
            if row.get("pe") != pe:
                row["pe"] = pe; changed.append("pe")
        div = _safe_float(row.get("dividends"))
        if div and div > 0:
            dy = round(div / price, 4)
            if row.get("dividend_yield") != dy:
                row["dividend_yield"] = dy; changed.append("dividend_yield")
        bv = _safe_float(row.get("bvps"))
        if bv and bv > 0:
            pb = round(price / bv, 2)
            if row.get("pb") != pb:
                row["pb"] = pb; changed.append("pb")
        return changed

    def refresh_all_data(self, tickers: list, progress=None,
                         deadline_s: float = 120.0, workers: int = 4) -> dict:
        """
        The 'Update Data' button's backend.

        Sources: kenyanstocks.com bulk table (fetched concurrently) and one live
        page per stock (afx.kwayisi.org, falling back to mystocks for the price).

        Never hangs: short timeouts, parallel fetch, hosts that cannot be reached
        are skipped after the first failure, a circuit breaker stops after a
        full round of failures, and a hard overall deadline applies.

        Consistency / accuracy rules:
          - Uploaded / researched fundamentals are authoritative: live data only
            FILLS empty fields (sources use different EPS bases - mixing them
            would make a stock's numbers disagree with each other).
          - P/E, dividend yield and P/B are recomputed from the fresh price and
            the stored EPS / dividend / book value.
          - Only a price fetched today is recorded (see snapshot_daily_prices).
          - last_update (fundamentals age) moves ONLY when live data filled a
            field; re-pricing ratios does not make old EPS "fresh".
          - Existing values are never blanked; data_source keeps the original
            source plus this run's notes (not an ever-growing history).
        """
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutTimeout
        from collections import Counter
        from services import nse_scraper as scraper

        def _progress(done, total, stage, current=""):
            if progress:
                try:
                    progress(done, total, stage, current)
                except Exception:
                    pass

        t0 = time.monotonic()
        now_iso = datetime.now().isoformat()
        today = datetime.now().strftime("%Y-%m-%d")
        bases = [t["ticker"].split(".")[0].upper() for t in tickers]
        total = len(bases)

        report = {
            "started_at": now_iso, "prices": None,
            "fundamentals": {"tickers_improved": 0, "fields_derived": 0, "errors": [],
                             "tickers_total": total, "tickers_live_ok": 0, "timed_out": []},
            "source_status": {}, "warnings": [],
        }

        scraper.reset_source_health()
        _progress(0, total, "prices")

        # 1. Bulk price table runs in the background WHILE the per-stock pages load.
        bulk_pool = ThreadPoolExecutor(max_workers=1)
        bulk_future = bulk_pool.submit(scraper.get_all_prices)

        # 2. One live page per stock, in parallel, with a circuit breaker.
        state = {"fails": 0, "oks": 0, "abort": False}
        state_lock = threading.Lock()
        errors = Counter()
        quotes = {}

        def _fetch(base):
            with state_lock:
                if state["abort"]:
                    return base, {}, "skipped"
            try:
                data, err = scraper.fetch_live_quote(base)
            except Exception as e:
                data, err = {}, f"{type(e).__name__}: {str(e)[:80]}"
            with state_lock:
                if data:
                    state["oks"] += 1; state["fails"] = 0
                else:
                    state["fails"] += 1
                    # A full round of parallel workers failing with not one
                    # success: the sources are blocked or down - stop waiting.
                    if state["fails"] >= max(3, workers) and state["oks"] == 0:
                        state["abort"] = True
            return base, data, err

        done = 0
        pool = ThreadPoolExecutor(max_workers=max(1, workers))
        futures = {pool.submit(_fetch, b): b for b in bases}
        try:
            remaining = max(1.0, deadline_s - (time.monotonic() - t0))
            for fut in as_completed(futures, timeout=remaining):
                b = futures[fut]
                try:
                    _, data, err = fut.result()
                except Exception as e:
                    data, err = {}, str(e)
                quotes[b] = data
                if not data and err and err != "skipped":
                    errors[err] += 1
                done += 1
                _progress(done, total, "fundamentals", b)
        except FutTimeout:
            for fut, b in futures.items():
                if b not in quotes:
                    fut.cancel()
                    report["fundamentals"]["timed_out"].append(b)
            report["warnings"].append(
                f"{len(report['fundamentals']['timed_out'])} stocks did not answer in time "
                "and kept their existing data.")
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

        bulk = {}
        try:
            bulk = bulk_future.result(timeout=max(1.0, deadline_s - (time.monotonic() - t0))) or {}
        except Exception as e:
            report["warnings"].append(f"Bulk price fetch failed: {type(e).__name__}: {str(e)[:80] or 'timed out'}")
        finally:
            bulk_pool.shutdown(wait=False, cancel_futures=True)
        fresh_bulk = {b: e for b, e in bulk.items() if _price_is_fresh_today(e, today)}

        live_ok = sum(1 for d in quotes.values() if d)
        if state["abort"]:
            top = errors.most_common(1)[0][0] if errors else "no response"
            report["warnings"].append(
                f"Per-stock sources are not reachable from the server ({top}). Stopped after "
                "repeated failures instead of waiting; existing data was left unchanged.")
        elif errors:
            top, _n = errors.most_common(1)[0]
            report["warnings"].append(f"{sum(errors.values())} stocks could not be fetched (mostly: {top}).")

        report["source_status"] = {
            "mansamarkets.com (bulk prices)": scraper.LAST_STATUS.get("mansamarkets.com", "not checked"),
            "kenyanstocks.com (bulk prices)": scraper.LAST_STATUS.get("kenyanstocks.com", "not checked"),
            "afx.kwayisi.org (per stock)": scraper.LAST_STATUS.get("afx.kwayisi.org", "not checked"),
            "live.mystocks.co.ke (price fallback)": scraper.LAST_STATUS.get("live.mystocks.co.ke", "not used"),
            "cross-check": scraper.LAST_STATUS.get("cross-check", "not run"),
            "stocks read": f"{live_ok}/{total}",
        }

        # 3. Record today's prices: bulk where fresh, else the live page price.
        prices_today = dict(fresh_bulk)
        for b, d in quotes.items():
            if b not in prices_today and d.get("price"):
                prices_today[b] = {"price": d["price"], "source": d.get("source", "live"),
                                   "updated_at": now_iso, "volume": 0, "price_date": d.get("price_date")}
        state, trade_date = market_clock()
        report["market"] = {"state": state, "trade_date": trade_date.isoformat()}
        try:
            report["prices"] = self.snapshot_daily_prices(prices_today, provisional=(state == "open"))
        except Exception as e:
            report["prices"] = {"available": False, "reason": str(e), "total_added": 0}
            report["warnings"].append(f"Price save failed: {e}")
        if not prices_today:
            report["warnings"].append(
                "No fresh prices were available today - showing last known prices. "
                "Upload a price CSV if you need today's values.")
        else:
            no_price = [b for b in bases if b not in prices_today]
            if no_price:
                shown = ", ".join(no_price[:12]) + (f" and {len(no_price) - 12} more" if len(no_price) > 12 else "")
                report["warnings"].append(
                    f"{len(no_price)} tracked stocks had no live price from any source and kept their "
                    f"last known price: {shown}.")
            suspect = report["prices"].get("skipped_suspect") or []
            if suspect:
                report["warnings"].append(
                    "Held back as implausible jumps (not saved - upload a CSV if the move is real, "
                    "e.g. after a split): " + "; ".join(suspect[:8]))
            if state == "open":
                report["warnings"].append(
                    "The market is open: these are live prices, recorded as provisional. "
                    "The official close is saved automatically after 16:00 Nairobi time.")

        with _mem_lock:
            current_prices = dict(self._prices)

        # 4. Merge: fill gaps only, reprice ratios, derive the rest.
        tickers_improved = 0
        fields_derived_total = 0
        for base in bases:
            live = quotes.get(base) or {}
            live_price, l_eps, l_pe = live.get("price"), live.get("eps"), live.get("pe")
            if live_price and l_eps and l_eps > 0 and l_pe and l_pe > 0 \
                    and abs(live_price / l_eps / l_pe - 1) > 0.15:
                # The source's own EPS, P/E and price contradict each other (sites mix bases, e.g.
                # group vs. company EPS). None of its fundamentals can be trusted - use the price only.
                live = {k: v for k, v in live.items() if k in ("price", "price_date", "source")}
                report["warnings"].append(f"{base}: the source's EPS, P/E and price contradict each other - "
                                          "its fundamentals were ignored (price still used).")
            with _mem_lock:
                existing = dict(self._fundamentals.get(base, {}))
            merged = dict(existing)

            filled = []
            for k in ("eps", "pe", "dividends", "dividend_yield", "market_cap"):
                v = live.get(k)
                if v is not None and merged.get(k) in (None, "", []):
                    merged[k] = v
                    filled.append(k)

            price = _price_of(current_prices.get(base))
            repriced = (self._reprice(merged, price, today)
                        if (price and not existing.get("check") and (live or fresh_bulk.get(base))) else [])

            merged["price"] = price
            derived_row, derived_fields = _derive_fundamentals_row(merged)
            derived_row.pop("price", None)

            if filled or repriced or derived_fields:
                notes = []
                if filled:
                    notes.append(f"live {today} ({live.get('source', 'live')}) filled: {', '.join(filled)}")
                if repriced:
                    notes.append(f"repriced {today} from current price: {', '.join(repriced)}")
                if derived_fields:
                    notes.append(f"derived {today}: {', '.join(derived_fields)}")
                derived_row["data_source"] = self._source_with(existing.get("data_source"), notes)
                if filled:
                    derived_row["last_update"] = today
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

        f = report["fundamentals"]
        f["tickers_improved"] = tickers_improved
        f["fields_derived"] = fields_derived_total
        f["tickers_live_ok"] = live_ok

        priced = report["prices"].get("total_added", 0) > 0 or bool(report["prices"].get("skipped_duplicate"))
        if live_ok == 0 and not priced:
            report["status"] = "no_live_data"
        elif report["warnings"]:
            report["status"] = "partial"
        else:
            report["status"] = "complete"
        report["completed_at"] = datetime.now().isoformat()
        report["duration_s"] = round(time.monotonic() - t0, 1)
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
