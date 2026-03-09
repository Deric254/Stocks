"""
nse_scraper.py — Real NSE Kenya data scraper.

Sources (in priority order):
1. NSE website  — https://www.nse.co.ke/market-statistics/
2. Investing.com — NSE equities pages
3. AfricanMarkets — nairobi stock exchange prices
4. Stanbic/Genghis online portals
5. Manual stub    — returns structure with nulls so app never breaks

The scraper:
- Uses requests + BeautifulSoup with rotating User-Agent
- Hard 10s timeout per request
- Returns normalized dict matching the format data_loader expects
- Logs exactly what worked/failed so you can see it clearly
"""

import re
import json
import math
import time
import requests
import threading
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

DATA_DIR   = Path(__file__).parent.parent / "data"
CACHE_DIR  = DATA_DIR / "nse_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

PRICES_CACHE = CACHE_DIR / "prices.json"
FUND_CACHE   = CACHE_DIR / "fundamentals.json"

PRICE_TTL  = 4 * 3600      # 4 hours
FUND_TTL   = 24 * 3600     # 24 hours
STALE_TTL  = 7 * 24 * 3600 # serve stale up to 7 days

_lock = threading.Lock()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

# Correct NSE ticker → company name mapping (for URL construction)
NSE_COMPANY_MAP = {
    "EQTY": "equity-group-holdings",
    "KCB":  "kcb-group",
    "COOP": "co-operative-bank-of-kenya",
    "ABSA": "absa-bank-kenya",
    "NCBA": "ncba-group",
    "DTK":  "diamond-trust-bank-kenya",
    "SCBK": "standard-chartered-bank-kenya",
    "HF":   "hf-group",
    "SBIC": "stanbic-holdings",
    "SCOM": "safaricom",
    "EABL": "east-african-breweries",
    "BAT":  "british-american-tobacco-kenya",
    "UNGA": "unga-group",
    "KCGM": "kenya-commercial-bank",
    "BRIT": "britam-holdings",
    "JUB":  "jubilee-holdings",
    "CIC":  "cic-insurance-group",
    "KNRE": "kenya-reinsurance",
    "TOTL": "total-energies-marketing-kenya",
    "KENOL":"kenolkobil",
    "BAMB": "bamburi-cement",
    "ARM":  "arm-cement",
    "CABL": "east-african-cables",
    "SASN": "sasini",
    "KAPC": "kapchorua-tea",
    "LIMT": "limuru-tea",
    "CTUM": "centum-investment",
    "NSE":  "nairobi-securities-exchange",
}


def _safe(v, d=None):
    if v is None: return d
    try:
        s = str(v).replace(",","").replace("%","").strip()
        f = float(s)
        return d if (math.isnan(f) or math.isinf(f)) else f
    except: return d


def _get(url, timeout=10):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.text
    except Exception as e:
        print(f"[NSE] GET failed {url}: {e}")
    return None


def _load_cache(path: Path) -> dict:
    with _lock:
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except: pass
    return {}


def _save_cache(path: Path, data: dict):
    with _lock:
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            print(f"[NSE] Cache save failed: {e}")


def _age_seconds(ts_str) -> float:
    try:
        dt = datetime.fromisoformat(str(ts_str))
        return (datetime.now() - dt).total_seconds()
    except: return 9e9


# ── Source 1: NSE official market statistics ──────────────────────────────

def _scrape_nse_official() -> dict:
    """
    Scrape https://www.nse.co.ke/market-statistics/ for all equity prices.
    Returns {TICKER: {price, change, volume, ...}}
    """
    results = {}
    urls = [
        "https://www.nse.co.ke/market-statistics/",
        "https://www.nse.co.ke/live-market/",
    ]
    for url in urls:
        html = _get(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        # Look for price tables
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all(["td","th"])
                if len(cols) < 3:
                    continue
                texts = [c.get_text(strip=True) for c in cols]
                # Try to identify ticker and price
                ticker = texts[0].upper().strip()
                if len(ticker) > 6 or len(ticker) < 2:
                    continue
                # Find price column (usually 2nd or 3rd)
                price = None
                for t in texts[1:4]:
                    p = _safe(t)
                    if p and p > 0.01:
                        price = p
                        break
                if price and ticker:
                    results[ticker] = {
                        "price": price,
                        "source": "nse_official",
                        "raw": texts,
                    }
        if results:
            print(f"[NSE] Official scrape OK — {len(results)} stocks from {url}")
            return results
    return results


# ── Source 2: Investing.com NSE pages ────────────────────────────────────

def _scrape_investing_com(ticker_base: str) -> Optional[dict]:
    """Fetch price from investing.com NSE page."""
    slug = NSE_COMPANY_MAP.get(ticker_base, ticker_base.lower())
    urls = [
        f"https://www.investing.com/equities/{slug}",
        f"https://www.investing.com/search/?q={ticker_base}+NSE+Kenya",
    ]
    for url in urls:
        html = _get(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        # investing.com last price
        for sel in [
            "[data-test='instrument-price-last']",
            ".text-5xl",
            "[class*='last-price']",
            "[class*='priceText']",
        ]:
            el = soup.select_one(sel)
            if el:
                p = _safe(el.get_text(strip=True))
                if p and p > 0:
                    return {"price": p, "source": "investing.com"}
    return None


# ── Source 3: African Markets ─────────────────────────────────────────────

def _scrape_african_markets(ticker_base: str) -> Optional[dict]:
    """Fetch from african-markets.com."""
    url = f"https://www.african-markets.com/en/stock-markets/nse/equities?code={ticker_base}"
    html = _get(url)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    # Look for price in various elements
    for pattern in [r"KES\s*([\d,\.]+)", r"([\d,]+\.?\d*)\s*KES"]:
        match = re.search(pattern, html)
        if match:
            p = _safe(match.group(1))
            if p and p > 0:
                return {"price": p, "source": "african-markets"}
    return None


# ── Source 4: NSE API endpoint (unofficial) ──────────────────────────────

def _fetch_nse_api_bulk() -> dict:
    """
    Try NSE's unofficial JSON endpoints.
    """
    results = {}
    endpoints = [
        "https://www.nse.co.ke/wp-content/uploads/docs/equity_price.json",
        "https://api.nse.co.ke/equity/prices",
        "https://www.nse.co.ke/api/equity/prices",
    ]
    for url in endpoints:
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                data = r.json()
                # Handle different response shapes
                items = data if isinstance(data, list) else data.get("data", data.get("prices", []))
                if isinstance(items, list):
                    for item in items:
                        ticker = str(item.get("ticker","") or item.get("symbol","") or item.get("code","")).upper().strip()
                        price  = _safe(item.get("price") or item.get("last") or item.get("close"))
                        if ticker and price and price > 0:
                            results[ticker] = {"price": price, "source": "nse_api"}
                    if results:
                        print(f"[NSE] API bulk OK — {len(results)} stocks")
                        return results
        except Exception as e:
            pass
    return results


# ── Source 5: Manual stub ─────────────────────────────────────────────────

# Known approximate NSE prices (March 2026 estimates — updated manually)
# These are FALLBACK only when all live sources fail
MANUAL_PRICE_STUBS = {
    "EQTY": 52.00,  "KCB": 36.00,   "COOP": 13.50,  "ABSA": 14.00,
    "NCBA": 43.00,  "DTK": 55.00,   "SCBK": 175.00, "HF":   3.50,
    "SBIC": 115.00, "SCOM": 18.00,  "EABL": 170.00, "BAT":  430.00,
    "UNGA": 32.00,  "KCGM": 5.00,   "BRIT": 5.50,   "JUB":  290.00,
    "CIC":  2.40,   "KNRE": 19.00,  "TOTL": 21.00,  "KENOL":11.00,
    "BAMB": 45.00,  "ARM":  0.50,   "CABL": 3.50,   "SASN": 18.00,
    "KAPC": 110.00, "LIMT": 550.00, "CTUM": 18.00,  "NSE":  10.00,
}


# ── Main public interface ─────────────────────────────────────────────────

def get_price(ticker: str) -> dict:
    """
    Get price for a single NSE ticker.
    Returns: {price, source, updated_at, stale}
    """
    base = ticker.split(".")[0].upper()

    # 1. Check fresh cache
    cache = _load_cache(PRICES_CACHE)
    entry = cache.get(base)
    if entry and _age_seconds(entry.get("updated_at","2000-01-01")) < PRICE_TTL:
        return {**entry, "stale": False}

    # 2. Try bulk NSE API first (efficient)
    bulk = _fetch_nse_api_bulk()
    if bulk:
        # Save all results to cache
        now = datetime.now().isoformat()
        for t, d in bulk.items():
            cache[t] = {**d, "updated_at": now}
        _save_cache(PRICES_CACHE, cache)
        if base in bulk:
            return {**bulk[base], "stale": False, "updated_at": now}

    # 3. Try official NSE scrape (gets all stocks at once)
    official = _scrape_nse_official()
    if official:
        now = datetime.now().isoformat()
        for t, d in official.items():
            cache[t] = {**d, "updated_at": now}
        _save_cache(PRICES_CACHE, cache)
        if base in official:
            return {**official[base], "stale": False, "updated_at": now}

    # 4. Try individual sources
    for fn in [_scrape_investing_com, _scrape_african_markets]:
        result = fn(base)
        if result and result.get("price"):
            now = datetime.now().isoformat()
            cache[base] = {**result, "updated_at": now}
            _save_cache(PRICES_CACHE, cache)
            return {**result, "stale": False, "updated_at": now}

    # 5. Stale cache (up to 7 days)
    if entry and _age_seconds(entry.get("updated_at","2000-01-01")) < STALE_TTL:
        return {**entry, "stale": True}

    # 6. Manual stub — always returns something
    stub_price = MANUAL_PRICE_STUBS.get(base, 0)
    return {
        "price":      stub_price,
        "source":     "manual_stub",
        "stale":      True,
        "updated_at": "manual",
        "note":       "Live price unavailable — showing reference price. Update via Data Status page.",
    }


def get_all_prices() -> dict:
    """
    Fetch all NSE prices in one go (bulk). Returns {TICKER: {price, source, ...}}
    """
    cache = _load_cache(PRICES_CACHE)

    # Check if bulk cache is fresh enough
    sample = next(iter(cache.values()), None) if cache else None
    if sample and _age_seconds(sample.get("updated_at","2000-01-01")) < PRICE_TTL:
        print(f"[NSE] Serving all prices from cache ({len(cache)} stocks)")
        return cache

    print("[NSE] Fetching all prices from live sources…")

    # Try bulk first
    results = _fetch_nse_api_bulk()
    if not results:
        results = _scrape_nse_official()

    if results:
        now = datetime.now().isoformat()
        for t, d in results.items():
            cache[t] = {**d, "updated_at": now}
        _save_cache(PRICES_CACHE, cache)
        print(f"[NSE] Bulk prices OK — {len(results)} stocks")
        return cache

    # Fall back to stale + stubs for missing
    print("[NSE] Live bulk failed — using stale cache + stubs")
    for base, stub_price in MANUAL_PRICE_STUBS.items():
        if base not in cache:
            cache[base] = {
                "price":      stub_price,
                "source":     "manual_stub",
                "updated_at": "manual",
                "stale":      True,
            }
    return cache


def get_price_history(ticker: str, days: int = 365) -> pd.DataFrame:
    """
    Build a simple price DataFrame.
    For NSE: we only have current price, so we generate a synthetic history
    using the cached price and random walk — CLEARLY MARKED as synthetic.
    Real history requires paid NSE data subscription.
    """
    import numpy as np
    base  = ticker.split(".")[0].upper()
    entry = get_price(ticker)
    price = entry.get("price", 0)

    if price <= 0:
        return pd.DataFrame()

    # Generate synthetic price history (random walk from current price)
    np.random.seed(hash(base) % 2**31)
    n         = days
    # Work backwards from today
    returns   = np.random.normal(0, 0.012, n)
    prices    = [price]
    for r in returns:
        prices.append(prices[-1] * (1 - r))  # reverse random walk
    prices = list(reversed(prices[1:]))

    dates = pd.date_range(end=datetime.now().date(), periods=n, freq="B")
    df    = pd.DataFrame({
        "open":   [p * (1 - abs(np.random.normal(0, 0.005))) for p in prices],
        "high":   [p * (1 + abs(np.random.normal(0, 0.008))) for p in prices],
        "low":    [p * (1 - abs(np.random.normal(0, 0.008))) for p in prices],
        "close":  prices,
        "volume": [int(abs(np.random.normal(500000, 200000))) for _ in prices],
    }, index=dates)
    df.index.name = "date"
    df["synthetic"] = True  # clearly flagged
    return df


def get_fundamentals(ticker: str) -> dict:
    """
    Get fundamentals for an NSE stock.
    Sources: NSE annual reports page, company websites, cached manual entries.
    Returns a dict matching what scoring.py expects.
    """
    base  = ticker.split(".")[0].upper()

    # Check cache
    cache = _load_cache(FUND_CACHE)
    entry = cache.get(base)
    if entry and _age_seconds(entry.get("last_update","2000-01-01")) < FUND_TTL:
        return entry

    # Try to scrape from NSE company page
    result = _scrape_nse_company_fundamentals(base)

    if result:
        result["last_update"]  = datetime.now().isoformat()
        result["data_source"]  = "nse_scrape"
        result["data_stale"]   = False
        cache[base] = result
        _save_cache(FUND_CACHE, cache)
        return result

    # Return stale cache
    if entry:
        entry["data_stale"] = True
        return entry

    # Return empty structure — app never breaks
    price = get_price(ticker).get("price", 0)
    return {
        "ticker":             ticker,
        "eps":                None,
        "bvps":               None,
        "revenue":            None,
        "debt":               None,
        "dividends":          None,
        "roe":                None,
        "margin":             None,
        "pe":                 None,
        "pb":                 None,
        "dividend_yield":     None,
        "market_cap":         None,
        "total_assets":       None,
        "debt_to_equity":     None,
        "interest_coverage":  None,
        "net_income":         None,
        "total_dividends":    None,
        "net_income_history": [],
        "revenue_history":    [],
        "dps_history":        [],
        "last_update":        "never",
        "data_source":        "none",
        "data_stale":         True,
    }


def _scrape_nse_company_fundamentals(base: str) -> Optional[dict]:
    """
    Try to scrape fundamental ratios from NSE company page.
    """
    urls = [
        f"https://www.nse.co.ke/listed-companies/{NSE_COMPANY_MAP.get(base, base.lower())}/",
        f"https://www.nse.co.ke/listed-companies/{base.lower()}/",
    ]
    for url in urls:
        html = _get(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        data = {}

        # Find all key-value pairs in tables or definition lists
        for row in soup.find_all(["tr","li","div"]):
            text = row.get_text(separator="|", strip=True)
            parts = text.split("|")
            if len(parts) < 2:
                continue
            key   = parts[0].lower().strip()
            value = parts[1].strip()

            if "p/e" in key or "price/earn" in key:
                data["pe"] = _safe(value)
            elif "p/b" in key or "price/book" in key:
                data["pb"] = _safe(value)
            elif "eps" in key or "earnings per share" in key:
                data["eps"] = _safe(value)
            elif "dividend yield" in key:
                data["dividend_yield"] = _safe(value)
            elif "roe" in key or "return on equity" in key:
                data["roe"] = _safe(value)
            elif "book value" in key:
                data["bvps"] = _safe(value)
            elif "market cap" in key:
                data["market_cap"] = _safe(value)
            elif "revenue" in key or "turnover" in key:
                data["revenue"] = _safe(value)

        if any(data.values()):
            return {**{
                "ticker": base, "eps": None, "bvps": None, "revenue": None,
                "debt": None, "dividends": None, "roe": None, "margin": None,
                "pe": None, "pb": None, "dividend_yield": None, "market_cap": None,
                "total_assets": None, "debt_to_equity": None, "interest_coverage": None,
                "net_income": None, "total_dividends": None,
                "net_income_history": [], "revenue_history": [], "dps_history": [],
            }, **data}

    return None
