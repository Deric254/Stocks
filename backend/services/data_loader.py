"""
data_loader.py — Clean data layer. Uses nse_scraper only. No Yahoo Finance.
JSON caching. Thread-safe. Never crashes.
"""
import json, math, threading, pandas as pd
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from services.nse_scraper import (
    get_price, get_all_prices, get_price_history,
    get_fundamentals as _scrape_fund
)

DATA_DIR  = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = DATA_DIR / "nse_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

WATCHLIST_JSON    = DATA_DIR / "watchlist.json"
MISSING_JSON      = DATA_DIR / "missing_data.json"
FETCH_STATUS_JSON = DATA_DIR / "fetch_status.json"

_lock = threading.Lock()

def _j(path, default):
    p = Path(path)
    if p.exists():
        try:
            with open(p) as f: return json.load(f)
        except: pass
    return default

def _w(path, data):
    with _lock:
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            print(f"[DL] write error {path}: {e}")

def _age_h(ts):
    try: return (datetime.now() - datetime.fromisoformat(str(ts))).total_seconds() / 3600
    except: return 9999.0


class DataLoader:
    def __init__(self): pass

    # ── Price ──────────────────────────────────────────────────────────────
    def get_price_data(self, ticker: str) -> pd.DataFrame:
        base = ticker.split(".")[0].upper()
        try:
            df = get_price_history(ticker, days=365)
            if df is not None and not df.empty:
                price = float(df["close"].iloc[-1])
                self._status(base, True, "nse_scraper", price)
                return df
        except Exception as e:
            print(f"[DL] price_history {base}: {e}")

        # Single-row stub so app never gets empty DF
        price = get_price(ticker).get("price", 0)
        self._status(base, False, "stub", price)
        if price > 0:
            idx = pd.DatetimeIndex([datetime.now()])
            return pd.DataFrame(
                {"open":[price],"high":[price],"low":[price],"close":[price],"volume":[0]},
                index=idx
            )
        return pd.DataFrame()

    # ── Fundamentals ───────────────────────────────────────────────────────
    def get_fundamentals(self, ticker: str) -> dict:
        base = ticker.split(".")[0].upper()
        try:
            fund = _scrape_fund(ticker)
            if fund:
                return self._inject(base, fund)
        except Exception as e:
            print(f"[DL] fundamentals {base}: {e}")
        return self._inject(base, self._empty(ticker))

    # ── Prefetch all at startup ────────────────────────────────────────────
    def prefetch_all(self, tickers: list):
        print(f"[prefetch] Bulk price fetch for {len(tickers)} stocks…")
        try:
            prices = get_all_prices()
            print(f"[prefetch] Got {len(prices)} stock prices")
        except Exception as e:
            print(f"[prefetch] Bulk prices error: {e}")

        def _f(meta):
            t = meta["ticker"]
            base = t.split(".")[0].upper()
            try:
                f  = _scrape_fund(t)
                ok = bool(f.get("pe") or f.get("eps") or f.get("roe"))
                print(f"[prefetch] {base}: {'OK' if ok else 'stub only'}")
            except Exception as e:
                print(f"[prefetch] {base}: {e}")

        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(_f, tickers))
        print("[prefetch] Complete.")

    # ── Data freshness for UI ──────────────────────────────────────────────
    def _status(self, base, ok, source, price=0):
        s = _j(FETCH_STATUS_JSON, {})
        s[base] = {
            "ok": ok, "source": source,
            "price": round(price, 2),
            "updated_at": datetime.now().isoformat()
        }
        _w(FETCH_STATUS_JSON, s)

    def get_data_freshness(self, tickers: list) -> list:
        status = _j(FETCH_STATUS_JSON, {})
        pc     = _j(CACHE_DIR / "prices.json", {})
        fc     = _j(CACHE_DIR / "fundamentals.json", {})

        # Load seed fundamentals to check what's available
        seed_path = Path(__file__).parent.parent / "data" / "nse_fundamentals_seed.json"
        seed = {}
        if seed_path.exists():
            try:
                import json
                with open(seed_path) as f:
                    raw = json.load(f)
                seed = {k: v for k, v in raw.items() if not k.startswith("_")}
            except Exception:
                pass

        CRITICAL_FIELDS = ["pe", "eps", "roe", "bvps", "dividend_yield"]
        result = []

        for meta in tickers:
            base      = meta["ticker"].split(".")[0].upper()
            p_entry   = pc.get(base, {})
            f_entry   = fc.get(base, {})
            s_entry   = seed.get(base, {})
            price_age = _age_h(p_entry.get("updated_at", "2000-01-01"))
            fund_age  = _age_h(f_entry.get("last_update", "2000-01-01"))
            price_val = p_entry.get("price", 0) or status.get(base, {}).get("price", 0)
            source    = p_entry.get("source", "unknown")

            # Price freshness
            if source == "manual_stub":   freshness, color = "stub",    "#ef4444"
            elif price_age < 4:           freshness, color = "live",    "#49A078"
            elif price_age < 24:          freshness, color = "today",   "#86efac"
            elif price_age < 168:         freshness, color = "stale",   "#facc15"
            else:                         freshness, color = "no_data", "#ef4444"

            # Fundamentals: prefer live cache, fall back to seed
            eff_fund = f_entry if f_entry.get("fetch_ok") else s_entry
            fund_source = f_entry.get("data_source", "none") if f_entry else "none"
            if fund_source == "none" and s_entry:
                fund_source = "seed_fy2024"
                fund_age = _age_h(s_entry.get("last_update", "2026-03-12"))

            # Per-field issues list — actionable
            issues = []
            for field in CRITICAL_FIELDS:
                val = eff_fund.get(field) if eff_fund else None
                if val is None:
                    issues.append({
                        "field":    field.upper(),
                        "severity": "critical",
                        "message":  f"Missing {field.upper()} — scoring reduced",
                        "fix":      "manual_entry",
                    })

            # Price issue
            if source == "manual_stub":
                issues.insert(0, {
                    "field":    "PRICE",
                    "severity": "warning",
                    "message":  "Using reference price — live fetch failed",
                    "fix":      "manual_price",
                })

            result.append({
                "ticker":       meta["ticker"],
                "name":         meta["name"],
                "sector":       meta["sector"],
                "price":        price_val,
                "source":       source,
                "freshness":    freshness,
                "color":        color,
                "price_age_h":  round(price_age, 1),
                "fund_age_h":   round(fund_age, 1),
                "fund_source":  fund_source,
                "updated_at":   p_entry.get("updated_at", "never"),
                "has_eps":      eff_fund.get("eps") is not None if eff_fund else False,
                "has_pe":       eff_fund.get("pe") is not None if eff_fund else False,
                "has_roe":      eff_fund.get("roe") is not None if eff_fund else False,
                "has_bvps":     eff_fund.get("bvps") is not None if eff_fund else False,
                "has_div":      eff_fund.get("dividend_yield") is not None if eff_fund else False,
                "issues":       issues,
                "issue_count":  len(issues),
            })
        return result

    # ── Watchlist ──────────────────────────────────────────────────────────
    def get_watchlist(self):
        return _j(WATCHLIST_JSON, [])

    def add_to_watchlist(self, ticker: str):
        wl = self.get_watchlist()
        if ticker not in wl:
            wl.append(ticker)
            _w(WATCHLIST_JSON, wl)
        return wl

    def remove_from_watchlist(self, ticker: str):
        wl = [x for x in self.get_watchlist() if x != ticker]
        _w(WATCHLIST_JSON, wl)
        return wl

    # ── Missing data manual entry ──────────────────────────────────────────
    def save_missing_field(self, ticker: str, field: str, value, source: str):
        base = ticker.split(".")[0].upper()
        d    = _j(MISSING_JSON, {})
        if base not in d:
            d[base] = {}
        d[base][field] = {
            "value": value, "source": source,
            "created_at": datetime.now().isoformat()
        }
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
            ("roe","ROE"),("pe","P/E"),("pb","P/B"),
            ("debt_to_equity","D/E"),("interest_coverage","Interest Coverage"),
            ("total_assets","Total Assets"),("market_cap","Market Cap"),
            ("net_income_history","5yr Net Income"),
            ("revenue_history","5yr Revenue"),("dps_history","5yr Dividends"),
        ]
        return [{"field":f,"label":l} for f,l in fields
                if not fund.get(f) or fund.get(f) == []]

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
        }
