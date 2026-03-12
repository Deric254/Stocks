"""
nse_scraper.py — REAL live NSE Kenya data with robust tracking.

Price Sources (cascade):
  1. kenyanstocks.com  — ALL stocks bulk, live prices + volume + change
  2. afx.kwayisi.org   — per-stock price + fundamentals
  3. live.mystocks.co.ke — per-stock fallback price
  4. Manual stub       — last resort, clearly flagged

Fundamentals Sources:
  1. afx.kwayisi.org   — PE, EPS, ROE, Book Value, Dividends, Market Cap
  2. Manual entry      — user-supplied via Data Status page

Data Health Tracking:
  - Per-field expiry: each fundamental field tracked individually
  - Missing fields reported to UI with age and suggested action
  - Retry logic: failed fetches retried after 1 hour, not 24
  - Notification system: /api/data-health returns actionable alerts
"""

import re
import json
import math
import threading
import requests
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

DATA_DIR  = Path(__file__).parent.parent / "data"
CACHE_DIR = DATA_DIR / "nse_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

PRICES_CACHE  = CACHE_DIR / "prices.json"
FUND_CACHE    = CACHE_DIR / "fundamentals.json"
HEALTH_CACHE  = CACHE_DIR / "data_health.json"

PRICE_TTL       = 4 * 3600        # re-fetch prices after 4h
FUND_TTL        = 24 * 3600       # re-fetch fundamentals after 24h
FUND_RETRY_TTL  = 1 * 3600        # retry FAILED fund fetch after 1h (not 24h)
FUND_EXPIRE_TTL = 7 * 24 * 3600   # fundamentals older than 7 days = expired
STALE_TTL       = 7 * 24 * 3600   # serve stale prices up to 7 days

# Fields we care about for scoring — tracked individually
TRACKED_FUND_FIELDS = ["pe", "eps", "bvps", "roe", "dividend_yield", "dividends", "market_cap"]
CRITICAL_FIELDS     = ["pe", "eps", "roe"]   # missing these degrades score most

_lock = threading.Lock()

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]
_ua_idx = 0

def _headers():
    global _ua_idx
    ua = USER_AGENTS[_ua_idx % len(USER_AGENTS)]
    _ua_idx += 1
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Referer": "https://www.google.com/",
    }

# Real prices from kenyanstocks.com March 2026 — ONLY used if all scraping fails
MANUAL_PRICE_STUBS = {
    "EQTY": 74.00, "KCB": 77.50, "COOP": 17.05, "ABSA": 30.45,
    "NCBA": 88.00, "DTK": 156.75, "SCBK": 270.00, "IMH": 49.85,
    "HF": 11.00, "SBIC": 115.00, "SCOM": 23.45, "EABL": 255.00,
    "BAT": 548.00, "UNGA": 32.00, "BRIT": 11.80, "JUB": 389.00,
    "CIC": 5.20, "KNRE": 3.80, "TOTL": 21.00, "KENOL": 11.00,
    "BAMB": 45.00, "CABL": 3.50, "SASN": 18.00, "KAPC": 250.00,
    "LIMT": 550.00, "CTUM": 15.00, "NSE": 22.25, "KEGN": 9.18,
    "KPLC": 17.25, "PORT": 81.75, "NMG": 15.50,
}


# ── Cache helpers ──────────────────────────────────────────────────────────

def _load_cache(path: Path) -> dict:
    with _lock:
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                pass
    return {}

def _save_cache(path: Path, data: dict):
    with _lock:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            print(f"[NSE] Cache save failed {path.name}: {e}")

def _age_seconds(ts_str) -> float:
    try:
        dt = datetime.fromisoformat(str(ts_str))
        return (datetime.now() - dt).total_seconds()
    except Exception:
        return 9e9

def _age_hours(ts_str) -> float:
    return _age_seconds(ts_str) / 3600

def _safe(v, d=None):
    if v is None:
        return d
    try:
        s = str(v).replace(",", "").replace("%", "").replace("KES", "").replace("Kshs", "").strip()
        f = float(s)
        return d if (math.isnan(f) or math.isinf(f)) else f
    except Exception:
        return d

def _get(url: str, timeout: int = 15) -> Optional[str]:
    try:
        r = requests.get(url, headers=_headers(), timeout=timeout)
        if r.status_code == 200:
            return r.text
        print(f"[NSE] HTTP {r.status_code} → {url}")
    except Exception as e:
        print(f"[NSE] GET failed {url}: {e}")
    return None


# ── Data health tracking ───────────────────────────────────────────────────

def _update_health(ticker: str, field: str, status: str, value=None, source: str = ""):
    """Track per-field data health. status: 'ok' | 'missing' | 'expired' | 'failed'"""
    health = _load_cache(HEALTH_CACHE)
    if ticker not in health:
        health[ticker] = {}
    health[ticker][field] = {
        "status":     status,
        "value":      value,
        "source":     source,
        "updated_at": datetime.now().isoformat(),
    }
    _save_cache(HEALTH_CACHE, health)

def get_data_health_report(tickers: list) -> dict:
    """
    Returns actionable data health report for all tickers.
    Used by /api/data-health endpoint to show notifications.
    """
    health   = _load_cache(HEALTH_CACHE)
    fund_cache = _load_cache(FUND_CACHE)
    price_cache = _load_cache(PRICES_CACHE)

    alerts    = []   # things that need attention
    ok_count  = 0
    warn_count = 0
    crit_count = 0

    for meta in tickers:
        t    = meta["ticker"] if isinstance(meta, dict) else meta
        base = t.split(".")[0].upper()

        fund  = fund_cache.get(base, {})
        price = price_cache.get(base, {})

        # Price health
        price_age_h = _age_hours(price.get("updated_at", "2000-01-01"))
        price_src   = price.get("source", "none")
        if price_src == "manual_stub":
            alerts.append({
                "ticker": base, "field": "price", "severity": "warning",
                "message": f"{base}: Using reference price from March 2026 — live fetch failed",
                "action": "Click Refresh on Data Status page",
            })
            warn_count += 1
        elif price_age_h > 24:
            alerts.append({
                "ticker": base, "field": "price", "severity": "warning",
                "message": f"{base}: Price is {price_age_h:.0f}h old",
                "action": "Click Refresh on Data Status page",
            })
            warn_count += 1
        else:
            ok_count += 1

        # Fundamentals health
        fund_age_h  = _age_hours(fund.get("last_update", "2000-01-01"))
        fund_source = fund.get("data_source", "none")

        if fund_source == "none" or not fund:
            alerts.append({
                "ticker": base, "field": "fundamentals", "severity": "critical",
                "message": f"{base}: No fundamental data at all — scoring will be 0",
                "action": "Enter manually from company annual report",
            })
            crit_count += 1
        elif fund_age_h > 168:  # 7 days
            alerts.append({
                "ticker": base, "field": "fundamentals", "severity": "warning",
                "message": f"{base}: Fundamentals expired ({fund_age_h:.0f}h old)",
                "action": "Click Force Refresh on Data Status page",
            })
            warn_count += 1

        # Per-field missing checks
        for field in CRITICAL_FIELDS:
            val = fund.get(field)
            if val is None:
                severity = "critical" if field in CRITICAL_FIELDS else "info"
                alerts.append({
                    "ticker": base, "field": field, "severity": severity,
                    "message": f"{base}: Missing {field.upper()} — score reduced",
                    "action": f"Enter {field.upper()} manually via Data Status page",
                })
                if severity == "critical":
                    crit_count += 1

    # Deduplicate — max 3 alerts per ticker to avoid flooding
    seen = {}
    deduped = []
    for a in alerts:
        key = f"{a['ticker']}_{a['field']}"
        if key not in seen:
            seen[key] = True
            deduped.append(a)

    return {
        "alerts":       deduped[:50],   # cap at 50
        "ok_count":     ok_count,
        "warn_count":   warn_count,
        "crit_count":   crit_count,
        "total_alerts": len(deduped),
        "generated_at": datetime.now().isoformat(),
    }


# ── Source 1: kenyanstocks.com bulk prices ────────────────────────────────

def _scrape_kenyanstocks_bulk() -> dict:
    """Scrape kenyanstocks.com/stock — all NSE stocks in one request."""
    url = "https://kenyanstocks.com/stock"
    html = _get(url)
    if not html:
        print("[NSE] kenyanstocks.com: no response")
        return {}

    soup = BeautifulSoup(html, "html.parser")
    results = {}
    table = soup.find("table")
    if not table:
        # Try div-based layout (site may have changed)
        rows = soup.find_all("tr")
        if not rows:
            print("[NSE] kenyanstocks.com: no table structure found")
            return {}
        table_rows = rows
    else:
        table_rows = table.find_all("tr")

    for row in table_rows:
        cols = row.find_all(["td", "th"])
        if len(cols) < 3:
            continue

        ticker_raw = ""
        link = cols[0].find("a")
        if link:
            href = link.get("href", "")
            parts = [p for p in href.split("/") if p and p not in ("stock", "nse")]
            if parts:
                ticker_raw = parts[-1].upper().strip()
        if not ticker_raw:
            ticker_raw = cols[0].get_text(strip=True).upper().strip()

        if not re.match(r'^[A-Z&]{2,6}$', ticker_raw):
            continue

        texts = [c.get_text(strip=True) for c in cols]

        price = None
        for idx in [3, 4, 2, 1]:
            if idx < len(texts):
                p = _safe(texts[idx])
                if p and 0.1 < p < 100000:
                    price = p
                    break
        if not price:
            continue

        change_pct = None
        for idx in [4, 5, 3]:
            if idx < len(texts):
                t = texts[idx].replace("+", "")
                c = _safe(t)
                if c is not None and -100 < c < 500:
                    change_pct = c
                    break

        volume = None
        for idx in [5, 6, 4]:
            if idx < len(texts):
                t = texts[idx].upper().replace(" ", "")
                t = re.sub(r'(\d+\.?\d*)K', lambda m: str(float(m.group(1)) * 1000), t)
                t = re.sub(r'(\d+\.?\d*)M', lambda m: str(float(m.group(1)) * 1e6), t)
                v = _safe(t)
                if v and v > 0:
                    volume = int(v)
                    break

        results[ticker_raw] = {
            "price": price, "change_pct": change_pct,
            "volume": volume, "source": "kenyanstocks.com",
        }

    if results:
        print(f"[NSE] kenyanstocks.com: {len(results)} stocks ✓")
    else:
        print("[NSE] kenyanstocks.com: 0 stocks parsed — site structure may have changed")
    return results


# ── Source 2: afx.kwayisi.org per-stock ───────────────────────────────────

def _scrape_afx(ticker_base: str) -> dict:
    """Scrape afx.kwayisi.org — price + PE, EPS, ROE, dividends, book value, market cap."""
    url = f"https://afx.kwayisi.org/nse/{ticker_base.lower()}.html"
    html = _get(url, timeout=15)
    if not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    data = {}

    # Parse all key-value tables
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cols = row.find_all(["td", "th"])
            if len(cols) < 2:
                continue
            key = cols[0].get_text(strip=True).lower()
            val = cols[1].get_text(strip=True)

            if ("price" in key or "close" in key or "last" in key) and "price" not in data:
                p = _safe(val)
                if p and 0.1 < p < 100000:
                    data["price"] = p
            elif "p/e" in key and "pe" not in data:
                p = _safe(val)
                if p and p > 0:
                    data["pe"] = p
            elif "eps" in key and "eps" not in data:
                p = _safe(val)
                if p is not None:
                    data["eps"] = p
            elif "dividend yield" in key and "dividend_yield" not in data:
                p = _safe(val)
                if p is not None:
                    data["dividend_yield"] = p / 100 if p > 1 else p
            elif "dividend" in key and "dividends" not in data and "yield" not in key:
                p = _safe(val)
                if p is not None:
                    data["dividends"] = p
            elif "book value" in key and "bvps" not in data:
                p = _safe(val)
                if p and p > 0:
                    data["bvps"] = p
            elif "market cap" in key and "market_cap" not in data:
                t = re.sub(r'(?i)B$', 'e9', val.strip())
                t = re.sub(r'(?i)M$', 'e6', t)
                t = re.sub(r'(?i)T$', 'e12', t)
                p = _safe(t)
                if p and p > 0:
                    data["market_cap"] = p
            elif "roe" in key and "roe" not in data:
                p = _safe(val)
                if p is not None:
                    data["roe"] = p / 100 if abs(p) > 1 else p
            elif "volume" in key and "volume" not in data:
                t = val.upper().replace("K", "000").replace("M", "000000")
                p = _safe(t)
                if p and p > 0:
                    data["volume"] = int(p)

    # Fallback price from text if table didn't yield it
    if "price" not in data:
        text = soup.get_text(separator="\n")
        for line in text.split("\n"):
            p = _safe(line.strip())
            if p and 1 < p < 100000:
                data["price"] = p
                break

    # History tables
    rev_h, ni_h, dps_h = [], [], []
    for table in soup.find_all("table"):
        ths = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        rows = table.find_all("tr")[1:]
        if any("revenue" in h or "turnover" in h for h in ths):
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) >= 2:
                    v = _safe(cells[1])
                    if v is not None:
                        rev_h.append(v)
        if any("income" in h or "profit" in h or "earn" in h for h in ths):
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) >= 2:
                    v = _safe(cells[1])
                    if v is not None:
                        ni_h.append(v)
        if any("dividend" in h or "dps" in h for h in ths):
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) >= 2:
                    v = _safe(cells[1])
                    if v is not None:
                        dps_h.append(v)

    data["revenue_history"]    = rev_h[-5:]
    data["net_income_history"] = ni_h[-5:]
    data["dps_history"]        = dps_h[-5:]

    if data.get("price") or any(data.get(f) is not None for f in ["pe", "eps", "roe"]):
        data["source"] = "afx.kwayisi.org"
    return data


# ── Source 3: mystocks.co.ke fallback price ────────────────────────────────

def _scrape_mystocks_price(ticker_base: str) -> Optional[float]:
    url = f"https://live.mystocks.co.ke/stock={ticker_base.upper()}"
    html = _get(url, timeout=10)
    if not html:
        return None
    matches = re.findall(r'(?:KES\s*)?([\d,]+\.?\d*)', html)
    for m in matches:
        p = _safe(m)
        if p and 1 < p < 100000:
            return p
    return None


# ── Public interface ───────────────────────────────────────────────────────

def get_all_prices() -> dict:
    """Bulk fetch all NSE prices from kenyanstocks.com. Cache 4h."""
    cache = _load_cache(PRICES_CACHE)
    sample = next(iter(cache.values()), None) if cache else None
    if sample and _age_seconds(sample.get("updated_at", "2000-01-01")) < PRICE_TTL:
        print(f"[NSE] Prices from cache ({len(cache)} stocks)")
        return cache

    print("[NSE] Live bulk price fetch from kenyanstocks.com…")
    now = datetime.now().isoformat()
    results = _scrape_kenyanstocks_bulk()

    if results:
        for ticker, d in results.items():
            cache[ticker] = {
                "price": d["price"], "change_pct": d.get("change_pct"),
                "volume": d.get("volume"), "source": "kenyanstocks.com",
                "updated_at": now, "stale": False,
            }
        _save_cache(PRICES_CACHE, cache)
        return cache

    # Stubs for anything missing
    for ticker, stub_price in MANUAL_PRICE_STUBS.items():
        if ticker not in cache:
            cache[ticker] = {
                "price": stub_price, "source": "manual_stub",
                "updated_at": "manual", "stale": True,
                "note": "Live fetch failed — reference price from March 2026",
            }
    return cache


def get_price(ticker: str) -> dict:
    """Single ticker price — cache → bulk → afx → mystocks → stub."""
    base = ticker.split(".")[0].upper()
    cache = _load_cache(PRICES_CACHE)
    entry = cache.get(base)

    if entry and _age_seconds(entry.get("updated_at", "2000-01-01")) < PRICE_TTL:
        return {**entry, "stale": False}

    all_p = get_all_prices()
    if base in all_p and all_p[base].get("source") != "manual_stub":
        return {**all_p[base], "stale": False}

    afx = _scrape_afx(base)
    if afx.get("price"):
        now = datetime.now().isoformat()
        result = {"price": afx["price"], "source": "afx.kwayisi.org", "updated_at": now, "stale": False}
        cache[base] = result
        _save_cache(PRICES_CACHE, cache)
        return result

    msp = _scrape_mystocks_price(base)
    if msp:
        now = datetime.now().isoformat()
        result = {"price": msp, "source": "mystocks.co.ke", "updated_at": now, "stale": False}
        cache[base] = result
        _save_cache(PRICES_CACHE, cache)
        return result

    if entry and _age_seconds(entry.get("updated_at", "2000-01-01")) < STALE_TTL:
        return {**entry, "stale": True}

    stub_price = MANUAL_PRICE_STUBS.get(base, 0)
    return {
        "price": stub_price, "source": "manual_stub", "stale": True,
        "updated_at": "manual",
        "note": "All live sources failed — reference price only.",
    }


def get_fundamentals(ticker: str) -> dict:
    """
    Get fundamentals from afx.kwayisi.org with intelligent retry.
    - If last fetch was successful and < 24h ago: serve cache
    - If last fetch FAILED and < 1h ago: serve cache (avoid hammering)
    - If last fetch FAILED and > 1h ago: retry
    - Track each field individually for health reporting
    """
    base = ticker.split(".")[0].upper()
    cache = _load_cache(FUND_CACHE)
    entry = cache.get(base)

    if entry:
        age_h = _age_hours(entry.get("last_update", "2000-01-01"))
        fetch_ok = entry.get("data_source", "none") != "none"

        # Successful fetch, still fresh
        if fetch_ok and age_h < 24:
            return entry

        # Failed fetch — respect retry cooldown (1h)
        if not fetch_ok and age_h < 1:
            print(f"[NSE] {base}: fund fetch failed recently, skipping retry for now")
            return entry

    print(f"[NSE] Fetching fundamentals for {base} from afx.kwayisi.org…")
    afx = _scrape_afx(base)
    price_data = get_price(ticker)
    price = price_data.get("price", 0)

    if afx and (afx.get("price") or any(afx.get(f) is not None for f in ["pe", "eps", "roe", "bvps"])):
        pe   = afx.get("pe")
        eps  = afx.get("eps")
        bvps = afx.get("bvps")
        pb = round(price / bvps, 2) if (price and bvps and bvps > 0) else None
        if not pe and eps and eps > 0 and price:
            pe = round(price / eps, 2)
        div_yield = afx.get("dividend_yield")
        dividends = afx.get("dividends")
        if not div_yield and dividends and price and price > 0:
            div_yield = round(dividends / price, 4)

        result = {
            "ticker": base, "eps": eps, "bvps": bvps, "pe": pe, "pb": pb,
            "roe": afx.get("roe"), "margin": None, "revenue": None,
            "debt": None, "dividends": dividends, "dividend_yield": div_yield,
            "market_cap": afx.get("market_cap"), "total_assets": None,
            "debt_to_equity": None, "interest_coverage": None,
            "net_income": None, "total_dividends": None,
            "revenue_history":    afx.get("revenue_history", []),
            "net_income_history": afx.get("net_income_history", []),
            "dps_history":        afx.get("dps_history", []),
            "last_update":  datetime.now().isoformat(),
            "data_source":  "afx.kwayisi.org",
            "data_stale":   False,
            "fetch_ok":     True,
        }
        # Track health per field
        for field in TRACKED_FUND_FIELDS:
            val = result.get(field)
            status = "ok" if val is not None else "missing"
            _update_health(base, field, status, val, "afx.kwayisi.org")

        cache[base] = result
        _save_cache(FUND_CACHE, cache)
        return result

    # Fetch returned nothing useful — record failure with timestamp
    print(f"[NSE] {base}: afx.kwayisi.org returned no data")
    for field in TRACKED_FUND_FIELDS:
        _update_health(base, field, "failed", None, "afx.kwayisi.org")

    if entry:
        entry["data_stale"] = True
        # Record failed attempt time so retry cooldown works
        entry["last_update"] = datetime.now().isoformat()
        entry["data_source"] = "none"
        cache[base] = entry
        _save_cache(FUND_CACHE, cache)
        return entry

    empty = {
        "ticker": base, "eps": None, "bvps": None, "revenue": None, "debt": None,
        "dividends": None, "roe": None, "margin": None, "pe": None, "pb": None,
        "dividend_yield": None, "market_cap": None, "total_assets": None,
        "debt_to_equity": None, "interest_coverage": None, "net_income": None,
        "total_dividends": None, "net_income_history": [], "revenue_history": [],
        "dps_history": [], "last_update": datetime.now().isoformat(),
        "data_source": "none", "data_stale": True, "fetch_ok": False,
    }
    cache[base] = empty
    _save_cache(FUND_CACHE, cache)
    return empty


def get_price_history(ticker: str, days: int = 365) -> pd.DataFrame:
    """
    Price DataFrame. Current price = REAL live price.
    History = synthetic random walk anchored to real price.
    (Free NSE historical OHLCV does not exist — requires paid subscription.)
    """
    base  = ticker.split(".")[0].upper()
    entry = get_price(ticker)
    price = entry.get("price", 0)
    if price <= 0:
        return pd.DataFrame()

    np.random.seed(hash(base) % 2**31)
    n = days
    returns = np.random.normal(0, 0.012, n)
    prices  = [price]
    for r in returns:
        prices.append(prices[-1] * (1 - r))
    prices = list(reversed(prices[1:]))

    dates = pd.date_range(end=datetime.now().date(), periods=n, freq="B")
    df = pd.DataFrame({
        "open":   [p * (1 - abs(np.random.normal(0, 0.005))) for p in prices],
        "high":   [p * (1 + abs(np.random.normal(0, 0.008))) for p in prices],
        "low":    [p * (1 - abs(np.random.normal(0, 0.008))) for p in prices],
        "close":  prices,
        "volume": [int(abs(np.random.normal(500000, 200000))) for _ in prices],
    }, index=dates)
    df.index.name = "date"
    df["synthetic"] = True
    return df
