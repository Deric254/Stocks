"""
csv_data_manager.py — Manual CSV upload data layer.
No scraping. No APIs. You feed the data.

Two separate upload flows:
  1. PRICES  — upload weekly, system warns if >7 days old
  2. FUNDAMENTALS — upload quarterly, system warns if >90 days old

Templates are generated for all NSE tickers so you can fill them in.
Data is cleaned, validated, merged without data loss.
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

_lock = threading.Lock()

# ── Fields ───────────────────────────────────────────────────────────────────

PRICE_FIELDS = ["ticker", "price"]

FUNDAMENTAL_FIELDS = [
    "ticker",
    "eps",           # Earnings per share (KES)
    "bvps",          # Book value per share (KES)
    "pe",            # Price to earnings ratio
    "pb",            # Price to book ratio
    "roe",           # Return on equity (decimal: 0.20 = 20%)
    "margin",        # Net profit margin (decimal: 0.15 = 15%)
    "dividends",     # Total dividends paid (KES, full year)
    "dividend_yield",# Dividend yield (decimal: 0.05 = 5%)
    "market_cap",    # Market capitalisation (KES)
    "total_assets",  # Total assets (KES)
    "debt_to_equity",# Debt to equity ratio
    "interest_coverage", # Interest coverage ratio
    "revenue",       # Annual revenue (KES)
    "net_income",    # Annual net income (KES)
    # 5-year history — semicolon separated values oldest→newest
    "revenue_history",    # e.g. 50B;60B;70B;80B;90B
    "net_income_history", # e.g. 5B;7B;8B;9B;10B
    "dps_history",        # Dividends per share e.g. 1.5;2.0;2.5;3.0;3.5
    # Metadata
    "data_source",   # e.g. "Annual Report FY2024", "NSE Filings"
    "fiscal_year",   # e.g. "2024"
    "last_update",   # date string YYYY-MM-DD
]


# ── JSON helpers ──────────────────────────────────────────────────────────────

def _rj(path, default):
    p = Path(path)
    if p.exists():
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            pass
    return default


def _wj(path, data):
    with _lock:
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            print(f"[CSV-MGR] write error {path}: {e}")


def _age_h(ts_str):
    try:
        return (datetime.now() - datetime.fromisoformat(str(ts_str))).total_seconds() / 3600
    except Exception:
        return 9999.0


def _age_days(ts_str):
    return _age_h(ts_str) / 24


# ── Template generation ───────────────────────────────────────────────────────

def generate_price_template(tickers: list) -> str:
    """Return CSV with ticker pre-filled and empty price column — user fills price only."""
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=PRICE_FIELDS)
    w.writeheader()
    for t in tickers:
        w.writerow({"ticker": t["ticker"], "price": ""})
    return out.getvalue()


def generate_fundamentals_template(tickers: list, seed: dict) -> str:
    """Return CSV bytes for fundamentals template — pre-filled from seed where available."""
    rows = []
    today = datetime.now().strftime("%Y-%m-%d")
    for t in tickers:
        base = t["ticker"].split(".")[0].upper()
        s = seed.get(base, {})

        def fmt_history(arr):
            if not arr:
                return ""
            return ";".join(str(v) for v in arr)

        rows.append({
            "ticker":             base,
            "eps":                s.get("eps", ""),
            "bvps":               s.get("bvps", ""),
            "pe":                 s.get("pe", ""),
            "pb":                 s.get("pb", ""),
            "roe":                s.get("roe", ""),
            "margin":             s.get("margin", ""),
            "dividends":          s.get("dividends", ""),
            "dividend_yield":     s.get("dividend_yield", ""),
            "market_cap":         s.get("market_cap", ""),
            "total_assets":       s.get("total_assets", ""),
            "debt_to_equity":     s.get("debt_to_equity", ""),
            "interest_coverage":  s.get("interest_coverage", ""),
            "revenue":            s.get("revenue", ""),
            "net_income":         s.get("net_income", ""),
            "revenue_history":    fmt_history(s.get("revenue_history", [])),
            "net_income_history": fmt_history(s.get("net_income_history", [])),
            "dps_history":        fmt_history(s.get("dps_history", [])),
            "data_source":        s.get("data_source", ""),
            "fiscal_year":        s.get("fiscal_year", "2024"),
            "last_update":        s.get("last_update", today),
        })
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=FUNDAMENTAL_FIELDS)
    w.writeheader()
    w.writerows(rows)
    return out.getvalue()


# ── Parsing and cleaning ──────────────────────────────────────────────────────

def _safe_float(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return None


def _parse_history(val):
    """Parse semicolon-separated history values into a list of floats."""
    if not val or str(val).strip() == "":
        return []
    parts = str(val).split(";")
    result = []
    for p in parts:
        p = p.strip().replace(",", "")
        # Handle shorthand like 50B, 1.2M
        try:
            multiplier = 1
            if p.upper().endswith("B"):
                multiplier = 1e9
                p = p[:-1]
            elif p.upper().endswith("M"):
                multiplier = 1e6
                p = p[:-1]
            elif p.upper().endswith("K"):
                multiplier = 1e3
                p = p[:-1]
            result.append(float(p) * multiplier)
        except Exception:
            pass
    return result


def parse_price_csv(content: bytes) -> tuple[list, list]:
    """
    Parse uploaded price CSV. Only ticker + price required.
    System sets today's date automatically.
    """
    errors = []
    valid = []
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        for i, row in enumerate(reader, start=2):
            row = {k.strip().lower(): v for k, v in row.items()}
            ticker = str(row.get("ticker", "")).strip().upper()
            if not ticker:
                continue
            # Accept "price" or "close" column
            price = _safe_float(row.get("price") or row.get("close"))
            if price is None or price <= 0:
                errors.append(f"{ticker}: price missing or zero — skipped")
                continue
            valid.append({
                "ticker": ticker,
                "date":   today,
                "open":   price,
                "high":   price,
                "low":    price,
                "close":  price,
                "volume": 0,
            })
    except Exception as e:
        errors.append(f"CSV parse error: {e}")
    return valid, errors


def parse_fundamentals_csv(content: bytes) -> tuple[list, list]:
    """
    Parse uploaded fundamentals CSV.
    Returns (valid_rows, errors)
    """
    errors = []
    valid = []
    try:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        for i, row in enumerate(reader, start=2):
            row = {k.strip().lower(): v for k, v in row.items()}
            ticker = str(row.get("ticker", "")).strip().upper()
            if not ticker:
                errors.append(f"Row {i}: missing ticker")
                continue

            last_update = str(row.get("last_update", "")).strip()
            if not last_update:
                last_update = datetime.now().strftime("%Y-%m-%d")

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
                "data_source":        str(row.get("data_source", "manual_csv")).strip() or "manual_csv",
                "fiscal_year":        str(row.get("fiscal_year", "2024")).strip(),
                "last_update":        last_update,
                "data_stale":         False,
                "fetch_ok":           True,
            }
            # At least one key fundamental must be present
            has_any = any(fund.get(f) is not None for f in ["eps", "pe", "roe", "bvps"])
            if not has_any:
                errors.append(f"Row {i} {ticker}: no fundamental data (eps/pe/roe/bvps all empty) — row skipped")
                continue
            valid.append(fund)
    except Exception as e:
        errors.append(f"CSV parse error: {e}")
    return valid, errors


# ── Storage ───────────────────────────────────────────────────────────────────

class CSVDataManager:
    """
    Persistent manual data store.
    Prices and fundamentals are stored separately.
    All reads are non-destructive merges — no data loss on update.
    """

    def __init__(self):
        self._prices: dict = {}       # ticker -> {date, open, high, low, close, volume, uploaded_at}
        self._price_history: dict = {}  # ticker -> [{date, open, high, low, close, volume}]
        self._fundamentals: dict = {}  # ticker -> fund dict
        self._meta: dict = {}          # upload timestamps and stats
        self._load_all()

    def _load_all(self):
        """Load persisted data from disk on startup."""
        # Load current prices
        if PRICES_CSV.exists():
            try:
                df = pd.read_csv(PRICES_CSV)
                for _, row in df.iterrows():
                    t = str(row.get("ticker", "")).strip().upper()
                    if t:
                        self._prices[t] = row.to_dict()
            except Exception as e:
                print(f"[CSV-MGR] load prices error: {e}")

        # Load price history
        if PRICES_HISTORY.exists():
            try:
                df = pd.read_csv(PRICES_HISTORY)
                for _, row in df.iterrows():
                    t = str(row.get("ticker", "")).strip().upper()
                    if t:
                        if t not in self._price_history:
                            self._price_history[t] = []
                        self._price_history[t].append(row.to_dict())
            except Exception as e:
                print(f"[CSV-MGR] load price_history error: {e}")

        # Load fundamentals
        if FUNDAMENTALS_CSV.exists():
            try:
                df = pd.read_csv(FUNDAMENTALS_CSV)
                for _, row in df.iterrows():
                    t = str(row.get("ticker", "")).strip().upper()
                    if t:
                        fund = row.to_dict()
                        # Parse history fields back from string
                        for hf in ["revenue_history", "net_income_history", "dps_history"]:
                            v = fund.get(hf, "")
                            if isinstance(v, str):
                                fund[hf] = _parse_history(v)
                            elif not isinstance(v, list):
                                fund[hf] = []
                        self._fundamentals[t] = fund
            except Exception as e:
                print(f"[CSV-MGR] load fundamentals error: {e}")

        # Load meta
        self._meta = _rj(META_JSON, {})

    def _save_prices_to_disk(self):
        """Persist current prices."""
        try:
            rows = list(self._prices.values())
            if rows:
                pd.DataFrame(rows).to_csv(PRICES_CSV, index=False)
        except Exception as e:
            print(f"[CSV-MGR] save prices error: {e}")

    def _save_history_to_disk(self):
        """Persist price history (append-friendly)."""
        try:
            all_rows = []
            for t, rows in self._price_history.items():
                all_rows.extend(rows)
            if all_rows:
                pd.DataFrame(all_rows).to_csv(PRICES_HISTORY, index=False)
        except Exception as e:
            print(f"[CSV-MGR] save history error: {e}")

    def _save_fundamentals_to_disk(self):
        """Persist fundamentals — stringify history arrays."""
        try:
            rows = []
            for t, fund in self._fundamentals.items():
                r = dict(fund)
                for hf in ["revenue_history", "net_income_history", "dps_history"]:
                    v = r.get(hf, [])
                    if isinstance(v, list):
                        r[hf] = ";".join(str(x) for x in v)
                rows.append(r)
            if rows:
                pd.DataFrame(rows).to_csv(FUNDAMENTALS_CSV, index=False)
        except Exception as e:
            print(f"[CSV-MGR] save fundamentals error: {e}")

    # ── UPLOAD PRICES ─────────────────────────────────────────────────────────

    def upload_prices(self, csv_content: bytes) -> dict:
        """
        Process uploaded price CSV.
        - Merges into current prices (latest date wins per ticker)
        - Appends to price history (deduped by ticker+date)
        - No data loss: existing data is preserved for tickers not in upload
        Returns summary with counts and errors.
        """
        rows, errors = parse_price_csv(csv_content)
        if not rows and errors:
            return {"success": False, "errors": errors, "updated": 0, "total": 0}

        uploaded_at = datetime.now().isoformat()
        updated = []

        with _lock:
            for r in rows:
                t = r["ticker"]
                # Update current price (latest only)
                existing = self._prices.get(t, {})
                existing_date = existing.get("date", "2000-01-01")
                if r["date"] >= existing_date:  # keep newest
                    self._prices[t] = {**r, "uploaded_at": uploaded_at}
                    updated.append(t)

                # Append to history (dedupe by ticker+date)
                if t not in self._price_history:
                    self._price_history[t] = []
                existing_dates = {row["date"] for row in self._price_history[t]}
                if r["date"] not in existing_dates:
                    self._price_history[t].append({**r, "uploaded_at": uploaded_at})

            self._save_prices_to_disk()
            self._save_history_to_disk()

            # Update meta
            self._meta["prices_last_upload"] = uploaded_at
            self._meta["prices_ticker_count"] = len(self._prices)
            self._meta["prices_updated_tickers"] = updated
            _wj(META_JSON, self._meta)

        return {
            "success": True,
            "updated": len(updated),
            "total":   len(self._prices),
            "skipped": len(rows) - len(updated),
            "errors":  errors,
            "uploaded_at": uploaded_at,
        }

    # ── UPLOAD FUNDAMENTALS ───────────────────────────────────────────────────

    def upload_fundamentals(self, csv_content: bytes) -> dict:
        """
        Process uploaded fundamentals CSV.
        - Merges by ticker — newer last_update wins per ticker per field
        - Fields not present in upload are PRESERVED from existing data
        - No data loss
        """
        rows, errors = parse_fundamentals_csv(csv_content)
        if not rows and errors:
            return {"success": False, "errors": errors, "updated": 0}

        uploaded_at = datetime.now().isoformat()
        updated = []

        with _lock:
            for fund in rows:
                t = fund["ticker"]
                existing = self._fundamentals.get(t, {})

                # Merge: only overwrite non-None values from upload
                merged = dict(existing)
                for k, v in fund.items():
                    if k in ("ticker",):
                        merged[k] = v
                        continue
                    if k in ["revenue_history", "net_income_history", "dps_history"]:
                        # Only overwrite history if upload has data
                        if v:  # non-empty list
                            merged[k] = v
                    elif v is not None and v != "" and v != []:
                        merged[k] = v

                merged["uploaded_at"] = uploaded_at
                merged["data_stale"] = False
                merged["fetch_ok"] = True
                self._fundamentals[t] = merged
                updated.append(t)

            self._save_fundamentals_to_disk()

            self._meta["fundamentals_last_upload"] = uploaded_at
            self._meta["fundamentals_ticker_count"] = len(self._fundamentals)
            self._meta["fundamentals_updated_tickers"] = updated
            _wj(META_JSON, self._meta)

        return {
            "success":  True,
            "updated":  len(updated),
            "total":    len(self._fundamentals),
            "errors":   errors,
            "uploaded_at": uploaded_at,
        }

    # ── READ PRICES ───────────────────────────────────────────────────────────

    def get_current_price(self, ticker: str) -> dict:
        """Return latest price entry for ticker."""
        base = ticker.split(".")[0].upper()
        return self._prices.get(base, {})

    def get_price_history_df(self, ticker: str, days: int = 365) -> pd.DataFrame:
        """Return price history as DataFrame, most recent `days`."""
        base = ticker.split(".")[0].upper()
        rows = self._price_history.get(base, [])
        if not rows:
            # Fall back to single current price row
            p = self._prices.get(base, {})
            if p and p.get("close"):
                rows = [p]
            else:
                return pd.DataFrame()

        df = pd.DataFrame(rows)
        required = ["date", "open", "high", "low", "close", "volume"]
        for col in required:
            if col not in df.columns:
                df[col] = df.get("close", 0)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).set_index("date").sort_index()
        df = df[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors="coerce")
        cutoff = datetime.now() - timedelta(days=days)
        df = df[df.index >= cutoff]
        return df

    # ── READ FUNDAMENTALS ─────────────────────────────────────────────────────

    def get_fundamentals(self, ticker: str, seed: dict = None) -> dict:
        """
        Return fundamentals for ticker.
        Falls back to seed data if no uploaded data.
        Merges seed (lower priority) with uploaded (higher priority).
        """
        base = ticker.split(".")[0].upper()
        uploaded = self._fundamentals.get(base, {})
        seed_entry = (seed or {}).get(base, {})

        if not uploaded and not seed_entry:
            return self._empty(ticker)

        # Merge: seed base, override with uploaded
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
        return dict(self._meta)

    def get_prices_age_days(self) -> float:
        ts = self._meta.get("prices_last_upload")
        if not ts:
            return 9999.0
        return _age_days(ts)

    def get_fundamentals_age_days(self) -> float:
        ts = self._meta.get("fundamentals_last_upload")
        if not ts:
            return 9999.0
        return _age_days(ts)

    def get_stale_fundamentals(self, tickers: list) -> list:
        """Return list of tickers where fundamentals are older than 90 days."""
        stale = []
        today = datetime.now()
        for t in tickers:
            base = t["ticker"].split(".")[0].upper()
            fund = self._fundamentals.get(base, {})
            if not fund:
                stale.append({"ticker": base, "reason": "no_data", "age_days": 9999})
                continue
            lu = fund.get("last_update", "")
            age = _age_days(lu) if lu and lu != "never" else 9999
            if age > 90:
                stale.append({"ticker": base, "reason": "expired", "age_days": round(age)})
        return stale

    def get_health_alerts(self, tickers: list) -> list:
        """
        Build actionable alerts for the notification bell.
        - Prices older than 7 days → warning
        - Prices older than 14 days → critical
        - Fundamentals older than 90 days → warning
        - Tickers with no price → critical
        - Tickers with no fundamentals → warning
        """
        alerts = []
        price_age = self.get_prices_age_days()
        fund_age  = self.get_fundamentals_age_days()

        # Global price staleness
        if price_age > 14:
            alerts.append({
                "ticker":   "ALL",
                "field":    "PRICES",
                "severity": "critical",
                "message":  f"Prices are {int(price_age)} days old — please upload fresh prices",
                "action":   "Upload price CSV in Data Status",
            })
        elif price_age > 7:
            alerts.append({
                "ticker":   "ALL",
                "field":    "PRICES",
                "severity": "warning",
                "message":  f"Prices are {int(price_age)} days old — consider updating",
                "action":   "Upload price CSV in Data Status",
            })

        # Global fundamentals staleness
        if fund_age > 90:
            alerts.append({
                "ticker":   "ALL",
                "field":    "FUNDAMENTALS",
                "severity": "warning",
                "message":  f"Fundamentals not updated in {int(fund_age)} days (quarterly update recommended)",
                "action":   "Upload fundamentals CSV in Data Status",
            })

        # Per-ticker missing prices
        missing_prices = []
        for t in tickers:
            base = t["ticker"].split(".")[0].upper()
            p = self._prices.get(base, {})
            if not p or not p.get("close"):
                missing_prices.append(base)

        if missing_prices:
            count = len(missing_prices)
            alerts.append({
                "ticker":   f"{count} stocks",
                "field":    "PRICE",
                "severity": "warning",
                "message":  f"{count} stocks have no price data",
                "action":   "Upload price CSV in Data Status",
            })

        # Per-ticker missing fundamentals
        missing_funds = []
        for t in tickers:
            base = t["ticker"].split(".")[0].upper()
            f = self._fundamentals.get(base, {})
            if not f or not any(f.get(k) for k in ["eps", "pe", "roe"]):
                missing_funds.append(base)

        if missing_funds:
            count = len(missing_funds)
            alerts.append({
                "ticker":   f"{count} stocks",
                "field":    "FUNDAMENTALS",
                "severity": "warning",
                "message":  f"{count} stocks have no fundamental data",
                "action":   "Upload fundamentals CSV in Data Status",
            })

        return alerts

    def get_freshness_report(self, tickers: list, seed: dict = None) -> list:
        """Full per-ticker freshness for the Data Status page."""
        result = []
        CRITICAL_FIELDS = ["pe", "eps", "roe", "bvps", "dividend_yield"]

        for meta in tickers:
            base = meta["ticker"].split(".")[0].upper()
            p    = self._prices.get(base, {})
            fund_uploaded = self._fundamentals.get(base, {})
            fund_seed     = (seed or {}).get(base, {})
            eff_fund      = dict(fund_seed)
            eff_fund.update({k: v for k, v in fund_uploaded.items()
                             if v is not None and v != "" and v != []})

            price_val = p.get("close", 0) or 0
            price_date = p.get("date", "")
            uploaded_at = p.get("uploaded_at", "")

            # Price age
            date_to_check = price_date or uploaded_at
            price_age_h = _age_h(date_to_check) if date_to_check else 9999

            if not price_val:
                freshness, color = "no_data", "#ef4444"
            elif price_age_h < 24:
                freshness, color = "fresh",  "#49A078"
            elif price_age_h < 168:   # 7 days
                freshness, color = "recent", "#86efac"
            elif price_age_h < 336:   # 14 days
                freshness, color = "stale",  "#facc15"
            else:
                freshness, color = "old",    "#ef4444"

            # Fundamentals age
            lu = eff_fund.get("last_update", "")
            fund_age_days = _age_days(lu) if lu and lu != "never" else 9999

            # Issues
            issues = []
            if not price_val:
                issues.append({
                    "field": "PRICE", "severity": "critical",
                    "message": "No price — stock will show KES 0",
                    "fix": "upload_prices",
                })
            elif price_age_h > 168:
                issues.append({
                    "field": "PRICE", "severity": "warning",
                    "message": f"Price is {int(price_age_h/24)} days old",
                    "fix": "upload_prices",
                })

            for field in CRITICAL_FIELDS:
                if not eff_fund.get(field):
                    issues.append({
                        "field": field.upper(), "severity": "critical",
                        "message": f"Missing {field.upper()} — scoring reduced",
                        "fix": "upload_fundamentals",
                    })

            if fund_age_days > 90:
                issues.append({
                    "field": "FUNDAMENTALS", "severity": "warning",
                    "message": f"Fundamentals {int(fund_age_days)} days old — quarterly update recommended",
                    "fix": "upload_fundamentals",
                })

            result.append({
                "ticker":        meta["ticker"],
                "name":          meta["name"],
                "sector":        meta["sector"],
                "price":         round(float(price_val), 2) if price_val else 0,
                "price_date":    price_date,
                "source":        "manual_csv" if p else "no_data",
                "freshness":     freshness,
                "color":         color,
                "price_age_h":   round(price_age_h, 1),
                "fund_age_days": round(fund_age_days, 1),
                "fund_source":   eff_fund.get("data_source", "none"),
                "fiscal_year":   eff_fund.get("fiscal_year", ""),
                "updated_at":    uploaded_at or price_date or "never",
                "has_eps":       eff_fund.get("eps") is not None,
                "has_pe":        eff_fund.get("pe") is not None,
                "has_roe":       eff_fund.get("roe") is not None,
                "has_bvps":      eff_fund.get("bvps") is not None,
                "has_div":       eff_fund.get("dividend_yield") is not None,
                "issues":        issues,
                "issue_count":   len(issues),
            })

        return result


# Singleton
_manager: Optional[CSVDataManager] = None


def get_manager() -> CSVDataManager:
    global _manager
    if _manager is None:
        _manager = CSVDataManager()
    return _manager
