"""
nse_scraper.py — REAL live NSE Kenya data.

Confirmed working sources (tested March 2026):
  1. kenyanstocks.com  — ALL stocks in one page, live prices + volume + change
  2. afx.kwayisi.org   — per-stock page with price + PE + EPS + dividends + history
  3. live.mystocks.co.ke — per-stock fallback price
  4. Manual stub       — absolute last resort (clearly flagged in UI)

Cache:
  nse_cache/prices.json       — refreshed every 4 hours
  nse_cache/fundamentals.json — refreshed every 24 hours
"""

import re
import json
import math
import threading
import requests
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path
from typing import Optional

DATA_DIR  = Path(__file__).parent.parent / "data"
CACHE_DIR = DATA_DIR / "nse_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

PRICES_CACHE = CACHE_DIR / "prices.json"
FUND_CACHE   = CACHE_DIR / "fundamentals.json"

PRICE_TTL  = 4 * 3600
FUND_TTL   = 24 * 3600
STALE_TTL  = 7 * 24 * 3600

_lock = threading.Lock()

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
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
    }

# Real March 2026 prices from kenyanstocks.com — only used if ALL scraping fails
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
            print(f"[NSE] Cache save failed: {e}")

def _age_seconds(ts_str) -> float:
    try:
        dt = datetime.fromisoformat(str(ts_str))
        return (datetime.now() - dt).total_seconds()
    except Exception:
        return 9e9

def _safe(v, d=None):
    if v is None:
        return d
    try:
        s = str(v).replace(",", "").replace("%", "").replace("KES", "").strip()
        f = float(s)
        return d if (math.isnan(f) or math.isinf(f)) else f
    except Exception:
        return d

def _get(url: str, timeout: int = 12) -> Optional[str]:
    try:
        r = requests.get(url, headers=_headers(), timeout=timeout)
        if r.status_code == 200:
            return r.text
        print(f"[NSE] HTTP {r.status_code} for {url}")
    except Exception as e:
        print(f"[NSE] GET failed {url}: {e}")
    return None


# ── Source 1: kenyanstocks.com bulk ───────────────────────────────────────

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
        print("[NSE] kenyanstocks.com: no table found in page")
        return {}

    for row in table.find_all("tr"):
        cols = row.find_all(["td", "th"])
        if len(cols) < 3:
            continue

        # Extract ticker from link href like /stock/nse/EQTY
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

        # Price is usually column 3 (Symbol | Company | Sector | Price | Change | Volume)
        price = None
        for idx in [3, 4, 2, 1]:
            if idx < len(texts):
                p = _safe(texts[idx])
                if p and 0.1 < p < 100000:
                    price = p
                    break
        if not price:
            continue

        # Change %
        change_pct = None
        for idx in [4, 5, 3]:
            if idx < len(texts):
                t = texts[idx].replace("+", "")
                c = _safe(t)
                if c is not None and -100 < c < 500:
                    change_pct = c
                    break

        # Volume
        volume = None
        for idx in [5, 6, 4]:
            if idx < len(texts):
                t = texts[idx].upper().replace(" ", "")
                t = re.sub(r'(\d+\.?\d*)K', lambda m: str(float(m.group(1)) * 1000), t)
                t = re.sub(r'(\d+\.?\d*)M', lambda m: str(float(m.group(1)) * 1000000), t)
                v = _safe(t)
                if v and v > 0:
                    volume = int(v)
                    break

        results[ticker_raw] = {
            "price": price,
            "change_pct": change_pct,
            "volume": volume,
            "source": "kenyanstocks.com",
        }

    if results:
        print(f"[NSE] kenyanstocks.com: got {len(results)} stocks ✓")
    else:
        print("[NSE] kenyanstocks.com: parsed 0 stocks — site may have changed structure")
    return results


# ── Source 2: afx.kwayisi.org per-stock ───────────────────────────────────

def _scrape_afx(ticker_base: str) -> dict:
    """Scrape afx.kwayisi.org for price + fundamentals."""
    url = f"https://afx.kwayisi.org/nse/{ticker_base.lower()}.html"
    html = _get(url)
    if not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    data = {}

    # Parse all tables
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
                data["pe"] = _safe(val)
            elif "eps" in key and "eps" not in data:
                data["eps"] = _safe(val)
            elif "dividend yield" in key and "dividend_yield" not in data:
                p = _safe(val)
                if p:
                    data["dividend_yield"] = p / 100 if p > 1 else p
            elif "dividend" in key and "dividends" not in data and "yield" not in key:
                data["dividends"] = _safe(val)
            elif "book value" in key and "bvps" not in data:
                data["bvps"] = _safe(val)
            elif "market cap" in key and "market_cap" not in data:
                t = re.sub(r'B$', 'e9', val, flags=re.I)
                t = re.sub(r'M$', 'e6', t, flags=re.I)
                data["market_cap"] = _safe(t)
            elif "roe" in key and "roe" not in data:
                p = _safe(val)
                if p:
                    data["roe"] = p / 100 if p > 1 else p
            elif "volume" in key and "volume" not in data:
                t = val.upper().replace("K","000").replace("M","000000")
                data["volume"] = _safe(t)

    # Also try text parsing for price if table failed
    if "price" not in data:
        text = soup.get_text(separator="\n")
        for line in text.split("\n"):
            p = _safe(line.strip())
            if p and 0.5 < p < 100000:
                data["price"] = p
                break

    # History tables (revenue, net income, dividends by year)
    rev_h, ni_h, dps_h = [], [], []
    for table in soup.find_all("table"):
        ths = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if any("revenue" in h or "turnover" in h for h in ths):
            for row in table.find_all("tr")[1:]:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) >= 2:
                    v = _safe(cells[1])
                    if v:
                        rev_h.append(v)
        if any("income" in h or "profit" in h or "earn" in h for h in ths):
            for row in table.find_all("tr")[1:]:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) >= 2:
                    v = _safe(cells[1])
                    if v:
                        ni_h.append(v)
        if any("dividend" in h or "dps" in h for h in ths):
            for row in table.find_all("tr")[1:]:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) >= 2:
                    v = _safe(cells[1])
                    if v:
                        dps_h.append(v)

    data["revenue_history"]    = rev_h[-5:]
    data["net_income_history"] = ni_h[-5:]
    data["dps_history"]        = dps_h[-5:]

    if data.get("price"):
        data["source"] = "afx.kwayisi.org"
    return data


# ── Source 3: mystocks.co.ke fallback ─────────────────────────────────────

def _scrape_mystocks_price(ticker_base: str) -> Optional[float]:
    url = f"https://live.mystocks.co.ke/stock={ticker_base.upper()}"
    html = _get(url)
    if not html:
        return None
    matches = re.findall(r'(?:KES\s*)?([\d,]+\.?\d*)', html)
    for m in matches:
        p = _safe(m)
        if p and 0.5 < p < 100000:
            return p
    return None


# ── Public interface ───────────────────────────────────────────────────────

def get_all_prices() -> dict:
    """Fetch all NSE prices — bulk from kenyanstocks.com, cache 4 hours."""
    cache = _load_cache(PRICES_CACHE)

    sample = next(iter(cache.values()), None) if cache else None
    if sample and _age_seconds(sample.get("updated_at", "2000-01-01")) < PRICE_TTL:
        print(f"[NSE] Prices from cache ({len(cache)} stocks)")
        return cache

    print("[NSE] Fetching live prices from kenyanstocks.com…")
    now = datetime.now().isoformat()
    results = _scrape_kenyanstocks_bulk()

    if results:
        for ticker, d in results.items():
            cache[ticker] = {
                "price":      d["price"],
                "change_pct": d.get("change_pct"),
                "volume":     d.get("volume"),
                "source":     "kenyanstocks.com",
                "updated_at": now,
                "stale":      False,
            }
        _save_cache(PRICES_CACHE, cache)
        return cache

    # Fill missing with stubs
    for ticker, stub_price in MANUAL_PRICE_STUBS.items():
        if ticker not in cache:
            cache[ticker] = {
                "price":      stub_price,
                "source":     "manual_stub",
                "updated_at": "manual",
                "stale":      True,
                "note":       "Live fetch failed — reference price from March 2026",
            }
    return cache


def get_price(ticker: str) -> dict:
    """Get price for a single ticker — cache, bulk, afx, mystocks, stub."""
    base = ticker.split(".")[0].upper()
    cache = _load_cache(PRICES_CACHE)
    entry = cache.get(base)

    if entry and _age_seconds(entry.get("updated_at", "2000-01-01")) < PRICE_TTL:
        return {**entry, "stale": False}

    all_p = get_all_prices()
    if base in all_p:
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
        "note": "All live sources failed — reference price only. Update via Data Status page.",
    }


def get_fundamentals(ticker: str) -> dict:
    """Get PE, EPS, ROE, dividends from afx.kwayisi.org."""
    base = ticker.split(".")[0].upper()
    cache = _load_cache(FUND_CACHE)
    entry = cache.get(base)

    if entry and _age_seconds(entry.get("last_update", "2000-01-01")) < FUND_TTL:
        return entry

    print(f"[NSE] Fetching fundamentals for {base}…")
    afx = _scrape_afx(base)
    price_data = get_price(ticker)
    price = price_data.get("price", 0)

    if afx:
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
        }
        cache[base] = result
        _save_cache(FUND_CACHE, cache)
        return result

    if entry:
        entry["data_stale"] = True
        return entry

    return {
        "ticker": base, "eps": None, "bvps": None, "revenue": None, "debt": None,
        "dividends": None, "roe": None, "margin": None, "pe": None, "pb": None,
        "dividend_yield": None, "market_cap": None, "total_assets": None,
        "debt_to_equity": None, "interest_coverage": None, "net_income": None,
        "total_dividends": None, "net_income_history": [], "revenue_history": [],
        "dps_history": [], "last_update": "never", "data_source": "none", "data_stale": True,
    }


def get_price_history(ticker: str, days: int = 365) -> pd.DataFrame:
    """
    Returns price DataFrame. Current price is REAL (live).
    Historical OHLCV is synthetic (NSE historical data is not free).
    Clearly flagged with synthetic=True column.
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
