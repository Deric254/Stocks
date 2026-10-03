"""
nse_scraper.py - live NSE Kenya quotes. Nothing here is guessed or hard-coded.

Sources
  1. mansamarkets.com + kenyanstocks.com - bulk tables, every stock in one request.
     Both are read and cross-checked; a stock they disagree on is dropped, not guessed.
  2. afx.kwayisi.org    - per-stock page: price + EPS, P/E, dividend, yield, market cap
  3. live.mystocks.co.ke- per-stock price fallback, used only when (2) gives nothing

A source that fails at connection level (DNS, refused, timeout) is marked
down for a short time so one dead host never costs a timeout per stock.
Every failure keeps its reason in LAST_STATUS so the Update report can say why.

Run `python -m services.nse_scraper` to see what each source returns from the
machine you run it on (useful when a host blocks your server's IP range).
"""

import json
import math
import random
import re
import threading
import time
from datetime import date, datetime, time as time_, timedelta, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup

from services.paths import DATA_DIR

CACHE_DIR = DATA_DIR / "nse_cache"
PRICES_CACHE = CACHE_DIR / "prices.json"
PRICE_TTL = 15 * 60           # bulk prices are re-fetched after 15 min (sites refresh ~every 30 min)

_lock = threading.Lock()
_local = threading.local()    # one requests.Session per thread: keep-alive without sharing state

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def _headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _session() -> requests.Session:
    s = getattr(_local, "session", None)
    if s is None:
        s = _local.session = requests.Session()
    return s


# -- Cache helpers ----------------------------------------------------------

def _load_cache(path) -> dict:
    with _lock:
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}


def _save_cache(path, data: dict):
    """Atomic write (temp file + rename): a crash never leaves a half-written cache."""
    with _lock:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2, default=str)
            tmp.replace(path)
        except OSError as e:
            print(f"[NSE] Cache save failed {path.name}: {e}")


def _age_seconds(ts_str) -> float:
    try:
        return (datetime.now() - datetime.fromisoformat(str(ts_str))).total_seconds()
    except (TypeError, ValueError):
        return 9e9


def _safe(v, d=None):
    if v is None:
        return d
    try:
        s = str(v).replace(",", "").replace("%", "").replace("KES", "").replace("Kshs", "").strip()
        f = float(s)
        return d if (math.isnan(f) or math.isinf(f)) else f
    except ValueError:
        return d


def last_trading_day(d: Optional[date] = None) -> date:
    """NSE trades Mon-Fri; on a weekend the latest real close is Friday's.
    With no argument: the trade date of the current Nairobi market session."""
    if d is None:
        return market_clock()[1]
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


# -- HTTP with fail-fast source tracking -----------------------------------

LAST_STATUS: dict = {}          # host -> last outcome, shown in the Update report
_DOWN_FOR_S = 120               # how long a host that cannot be reached is skipped
_down_until: dict = {}          # host -> monotonic time until which it is skipped


def reset_source_health():
    """Forget which hosts were marked down (called at the start of each Update)."""
    _down_until.clear()


def _describe_error(exc: Exception) -> tuple:
    """(short human reason, is_connection_level). Looks at the whole error text -
    requests wraps the real cause deep inside 'Max retries exceeded'."""
    text = str(exc)
    low = text.lower()
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return "connection timed out", True
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return "server too slow (read timed out)", False
    if isinstance(exc, requests.exceptions.SSLError):
        return "TLS/SSL handshake failed", True
    if any(k in low for k in ("name or service not known", "nameresolution", "getaddrinfo",
                              "temporary failure in name resolution", "nodename nor servname")):
        return "DNS lookup failed (host name does not resolve from this server)", True
    if "refused" in low:
        return "connection refused", True
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "connection failed (" + type(exc).__name__ + ")", True
    return f"{type(exc).__name__}: {text[:80]}", False


def _get_ex(url: str, timeout=(5, 12), attempts: int = 2):
    """GET -> (html, error). Short timeouts; retries only what a retry can fix
    (slow reads, 5xx). Connection-level failures mark the host down so the
    next stocks skip it instantly instead of each waiting for a timeout."""
    host = url.split("/")[2] if "//" in url else url
    if _down_until.get(host, 0) > time.monotonic():
        return None, LAST_STATUS.get(host, "source unreachable") + " (skipped)"

    err = "unknown error"
    for i in range(attempts):
        try:
            r = _session().get(url, headers=_headers(), timeout=timeout)
            if r.status_code == 200:
                LAST_STATUS[host] = "ok"
                return r.text, None
            err = f"HTTP {r.status_code}"
            if r.status_code < 500 and r.status_code != 429:
                break                     # 403/404/...: retrying will not help
        except requests.exceptions.RequestException as e:
            err, connection_level = _describe_error(e)
            if connection_level:
                _down_until[host] = time.monotonic() + _DOWN_FOR_S
                break
        if i + 1 < attempts:
            time.sleep(1.0)
    LAST_STATUS[host] = err
    print(f"[NSE] GET failed {url}: {err}")
    return None, err


# -- Market clock ---------------------------------------------------------------
EAT = timezone(timedelta(hours=3))
OPEN_H, CLOSE_H, FINAL_AFTER = time_(9, 0), time_(15, 0), time_(16, 0)


def market_clock(now: Optional[datetime] = None) -> tuple:
    """(state, trade_date) in Nairobi time. state: 'pre' (before 09:00), 'open'
    (until 16:00: the close is 15:00 but sites lag up to ~30 min, so prices are not final yet) or 'closed' (final). A price seen
    before the open is yesterday's close, so its trade_date is the previous
    trading day; weekends roll back to Friday. (Public holidays are not known.)"""
    now = (now or datetime.now(EAT)).astimezone(EAT)
    d, t = now.date(), now.time()
    if d.weekday() >= 5:
        return "closed", last_trading_day(d)
    if t < OPEN_H:
        return "pre", last_trading_day(d - timedelta(days=1))
    return ("open" if t < FINAL_AFTER else "closed"), d


# -- Bulk price tables (kenyanstocks.com, mansamarkets.com) --------------------

TICKER_ALIASES = {"HFCB": "HFCK"}   # sites use the new HF Group symbol; the app tracks HFCK
_NOT_TICKERS = {"STOCK", "STOCKS", "KENYA", "COMPANIES", "MARKETS"}
_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def _to_number(text) -> Optional[float]:
    """'KSh1,250.00' -> 1250.0, '−1.35%' -> -1.35 (Unicode minus), '2.41M' -> 2410000.0,
    '6.27 K' -> 6270.0. Anything else (including '—') -> None."""
    t = str(text).replace("\u2212", "-").replace("\u2013", "-").replace(",", "").replace("%", "")
    t = re.sub(r"(?i)kshs?|kes", "", t).replace("+", "").strip()
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s?([KMBT]?)", t, re.I)
    if not m:
        return None
    return float(m.group(1)) * _MULT.get(m.group(2).upper(), 1.0)


def _cell_label(cell) -> str:
    """Header text of a table cell, falling back to aria-label/title/img alt
    for headers drawn as icons or buttons."""
    text = cell.get_text(" ", strip=True)
    if not text:
        text = cell.get("aria-label") or cell.get("title") or ""
        if not text:
            img = cell.find("img", alt=True)
            text = img["alt"] if img else ""
    return text.strip().lower()


def _detect_columns(headers: list) -> dict:
    """Map lower-cased header texts to {"price"|"change"|"volume": index}. First match
    wins. "change" is tested before "price" so a "Price Change" column is never mistaken
    for the price, and previous/open/high/low price columns are never the current price.
    When a table has both an absolute "Change" (+0.50) and a percentage "Chg %" (+1.39%),
    the percentage column is the one returned as "change"."""
    cols, pct_col = {}, None
    for i, h in enumerate(headers):
        if "%" in h:
            if pct_col is None:
                pct_col = i
            continue
        if "change" in h or "chg" in h:
            key = "change"
        elif "vol" in h:
            key = "volume"
        elif "price" in h and not any(w in h for w in ("prev", "open", "high", "low")):
            key = "price"
        else:
            continue
        cols.setdefault(key, i)
    if pct_col is not None:
        cols["change"] = pct_col
    return cols


def _row_ticker(row) -> str:
    """Ticker of a table row: the last path segment of the row's first usable link
    (/kenya/scom, /stock/nse), else the text of the first cell that is a bare ticker."""
    for link in row.find_all("a", href=True):
        seg = link["href"].split("?")[0].rstrip("/").split("/")[-1].upper().strip()
        if re.fullmatch(r"[A-Z&]{2,7}", seg) and seg not in _NOT_TICKERS:
            return seg
    for cell in row.find_all(["td", "th"]):
        txt = cell.get_text(strip=True).upper()
        if re.fullmatch(r"[A-Z&]{2,7}", txt) and txt not in _NOT_TICKERS:
            return txt
    return ""


def _page_date(text: str) -> Optional[date]:
    """The market date a page says it shows ('on Thursday, 1 October 2026',
    'Updated 1 Oct 2026'), or None when it does not say."""
    m = re.search(r"(?:on (?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,|Updated|Last updated)\s+"
                  r"(\d{1,2}) ([A-Za-z]{3})[a-z]* (\d{4})", text)
    if not m or m.group(2).lower() not in _MONTHS:
        return None
    try:
        return date(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))
    except ValueError:
        return None


def _parse_price_table(html: str, source: str) -> dict:
    """Parse the price table of a bulk page. The table is found by its HEADER TEXT
    (it needs a Price column), every column is located from that header, and nothing
    is guessed: if the page cannot be read, LAST_STATUS[source] says exactly why.
    Rows that did not trade today (no change and no volume) are not 'today's price'
    and are skipped. A page dated before the latest trading day (a stale cached page)
    is rejected."""
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        LAST_STATUS[source] = ("page has no price table - the site now builds it with "
                               "JavaScript, so a plain request cannot read it")
        return {}

    table, cols, seen = None, {}, []
    for t in tables:
        first = t.find("tr")
        if first is None:
            continue
        headers = [_cell_label(c) for c in first.find_all(["th", "td"])]
        seen.append(headers)
        found = _detect_columns(headers)
        if "price" in found:
            table, cols = t, found
            break
    if table is None:
        if seen and all(not any(h) for h in seen):
            LAST_STATUS[source] = ("page has only empty placeholder tables - the real price table is "
                                   "filled in by JavaScript, which a plain request cannot run")
        else:
            LAST_STATUS[source] = f"page loaded but no table has a Price column (headers seen: {seen[:3]})"
        return {}

    page_day = _page_date(soup.get_text(" ", strip=True))
    latest = market_clock()[1]
    if page_day is not None and not latest - timedelta(days=4) <= page_day <= latest:
        LAST_STATUS[source] = f"page is dated {page_day.isoformat()}, not the latest trading day - ignored"
        return {}

    price_col, change_col, volume_col = cols["price"], cols.get("change"), cols.get("volume")
    results, untraded = {}, 0
    for row in table.find_all("tr")[1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) <= price_col:
            continue
        ticker = _row_ticker(row)
        if not ticker:
            continue
        texts = [c.get_text(strip=True) for c in cells]

        price = _to_number(texts[price_col])
        if not price or not 0.10 < price < 100000:
            continue
        change_pct = volume = None
        if change_col is not None and change_col < len(texts):
            c = _to_number(texts[change_col])
            if c is not None and -50 < c < 50:       # realistic daily change range
                change_pct = c
        if volume_col is not None and volume_col < len(texts):
            v = _to_number(texts[volume_col])
            if v and v > 0:
                volume = int(v)
        if (change_col is not None or volume_col is not None) and change_pct is None and volume is None:
            untraded += 1
            continue
        res = {"price": price, "change_pct": change_pct, "volume": volume, "source": source}
        if page_day is not None:
            res["price_date"] = page_day.isoformat()
        results[TICKER_ALIASES.get(ticker, ticker)] = res

    if results:
        extra = f", {untraded} did not trade today" if untraded else ""
        LAST_STATUS[source] = f"ok - {len(results)} stocks read{extra}"
    else:
        LAST_STATUS[source] = (f"page loaded and a price table was found, but 0 rows could be read "
                               f"(headers: {seen[-1]})")
    return results


def _scrape_bulk(source: str, url: str) -> dict:
    html, err = _get_ex(url)
    if not html:
        LAST_STATUS[source] = err or "no response"
        return {}
    return _parse_price_table(html, source)


def _scrape_mansa() -> dict:
    return _scrape_bulk("mansamarkets.com", "https://www.mansamarkets.com/kenya")


def _scrape_kenyanstocks_bulk() -> dict:
    return _scrape_bulk("kenyanstocks.com", "https://kenyanstocks.com/stock")


def _bulk_sources() -> list:
    """(name, scraper) in priority order. Resolved at call time."""
    return [("mansamarkets.com", _scrape_mansa), ("kenyanstocks.com", _scrape_kenyanstocks_bulk)]


DISAGREE_PCT = 5.0   # two sources differing by more than this are not trusted


def _combine(per_source: dict) -> tuple:
    """Merge bulk results from several sources. A price is accepted when only one
    source has it, or when every source that has it agrees within DISAGREE_PCT.
    A disagreement drops that ticker for today (never a guess) and is reported."""
    merged, disputed = {}, []
    for name, rows in per_source.items():
        for t, d in rows.items():
            if t not in merged:
                merged[t] = {**d, "source": d.get("source", name), "confirmed_by": []}
                continue
            first = merged[t]
            if abs(d["price"] - first["price"]) / first["price"] * 100 > DISAGREE_PCT:
                disputed.append(f"{t} ({first['source']} {first['price']} vs {name} {d['price']})")
                first["disputed"] = True
            else:
                first["confirmed_by"].append(name)
    for t in [t for t, d in merged.items() if d.get("disputed")]:
        del merged[t]
    return merged, disputed


_NUM = r'(-?[\d,]*\.?\d+)\s?([%BMKT]?)(?![A-Za-z])'
_AFX_LABELS = {
    "eps":            r'(?i:earnings per share)',
    "pe":             r'(?i:price/earning ratio)',
    "dividends":      r'(?i:dividend per share)',
    "dividend_yield": r'(?i:dividend yield)',
    "market_cap":     r'(?i:market capitali[sz]ation)',
}
_MULT = {"": 1.0, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def _parse_afx_html(html: str) -> dict:
    """
    Parse one afx.kwayisi.org stock page. Reads the page text by its LABELS
    (never by position) and converts units to what the rest of the app uses:
    dividend_yield as a fraction (2.5% -> 0.025), market_cap in absolute KES.

    Two bugs fixed vs the old parser:
      * the old code took the first row containing "price" - that is
        "Opening Price", NOT the current price. The current price now comes
        from the page's own "current share price ... is KES X" sentence.
      * the old code looked for the label "p/e", but the site says
        "Price/Earning Ratio", so PE was never found; EPS, dividends, yield
        and market cap were never parsed at all.
    A field that is blank on the page stays absent - nothing is guessed.
    """
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    data = {}

    m = re.search(r'current share price of .{3,160}? is KES\s*([\d,]+\.?\d*)', text, re.S | re.I)
    if m:
        p = _safe(m.group(1))
        if p and 0.1 < p < 100000:
            data["price"] = p

    for field, label in _AFX_LABELS.items():
        m = re.search(label + r'\s*' + _NUM, text)
        if not m:
            continue
        v = _safe(m.group(1))
        if v is None:
            continue
        suffix = m.group(2)
        if suffix == "%":
            v = v / 100.0
        elif suffix in _MULT:
            v = v * _MULT[suffix]
        if field == "pe" and not (0 < v < 1000):
            continue
        if field == "dividend_yield" and not (0 <= v < 1):
            continue
        if field == "market_cap" and v <= 0:
            continue
        data[field] = v

    if data:
        data["source"] = "afx.kwayisi.org"
    return data


def fetch_live_quote(ticker_base: str):
    """One stock -> (data, error). afx first (price + fundamentals), then the
    mystocks price fallback. data is {} when nothing usable was found; error says why."""
    base = ticker_base.lower()
    html, err = _get_ex(f"https://afx.kwayisi.org/nse/{base}.html")
    if html:
        data = _parse_afx_html(html)
        if data:
            return data, None
        err = "page loaded but no price/fundamentals found (site layout may have changed)"

    html2, err2 = _get_ex(f"https://live.mystocks.co.ke/stock={ticker_base.upper()}", timeout=(5, 10), attempts=1)
    if html2:
        data = _parse_mystocks_html(html2)
        if data:
            return data, None
        err2 = "no current-day quote on page"
    return {}, f"afx: {err}; mystocks: {err2}"


# -- Source 3: live.mystocks.co.ke -----------------------------------------

_MYSTOCKS_QUOTE = re.compile(
    r'(?:End of day|Delayed|Real[- ]?time)\s*-\s*([A-Z][a-z]{2}) (\d{1,2}), (\d{4})\s+'
    r'([\d,]+(?:\.\d+)?)\s+[+-]?[\d,.]+\s*\(')


def _parse_mystocks_html(html: str, today: Optional[date] = None) -> dict:
    """Read the quote header ("End of day - Aug 05, 2026  25.05  -0.60 (-2.34%)").
    The quote carries its own date; a quote that is not for the latest trading
    day is rejected instead of being passed off as today's price."""
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    m = _MYSTOCKS_QUOTE.search(text)
    if not m:
        return {}
    try:
        quote_day = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y").date()
    except ValueError:
        return {}
    if quote_day != last_trading_day(today):
        return {}
    price = _safe(m.group(4))
    if not price or not 0.1 < price < 100000:
        return {}
    return {"price": price, "price_date": quote_day.isoformat(), "source": "live.mystocks.co.ke"}


# -- Public interface ------------------------------------------------------

def get_all_prices(max_age_s: float = PRICE_TTL) -> dict:
    """Bulk NSE prices merged from every working bulk source and cross-checked
    (see _combine). Cached for max_age_s. Returns only real, timestamped scraped
    prices (possibly old ones from the cache - callers that need today's prices
    must check updated_at). Never invents a price."""
    cache = _load_cache(PRICES_CACHE)
    names = {n for n, _ in _bulk_sources()}
    newest = min((_age_seconds(e.get("updated_at")) for e in cache.values()
                  if e.get("source") in names), default=None)
    if newest is not None and newest < max_age_s:
        return cache

    per_source = {}
    for name, scrape in _bulk_sources():
        rows = scrape()
        if rows:
            per_source[name] = rows
    merged, disputed = _combine(per_source)
    LAST_STATUS["cross-check"] = (
        "disagreement, dropped for today: " + "; ".join(disputed) if disputed else
        f"{len(per_source)} bulk source(s) agreed" if len(per_source) > 1 else
        "only one bulk source available - prices not cross-checked")
    if merged:
        now = datetime.now().isoformat()
        for ticker, d in merged.items():
            cache[ticker] = {"price": d["price"], "change_pct": d.get("change_pct"),
                             "volume": d.get("volume"), "source": d["source"],
                             "confirmed_by": d["confirmed_by"], "price_date": d.get("price_date"),
                             "updated_at": now, "stale": False}
        _save_cache(PRICES_CACHE, cache)
    return cache


def check_sources() -> dict:
    """Probe every source from THIS machine and say, in plain terms, whether automatic
    updates will work here. Safe to run any time (read-only, nothing is saved).
    verdict: 'ready' (>=2 bulk sources readable: prices are cross-checked), 'degraded'
    (exactly 1 bulk source: works, but unverified by a second source) or 'blocked'
    (no bulk source readable: use Paste prices / CSV)."""
    reset_source_health()
    sources = []
    for name, scrape in _bulk_sources():
        t0 = time.monotonic()
        rows = scrape()
        sample = {k: rows[k]["price"] for k in ("SCOM", "EQTY", "KCB") if k in rows}
        sources.append({"source": name, "kind": "bulk", "ok": len(rows) >= 30, "rows": len(rows),
                        "detail": LAST_STATUS.get(name, "no response"), "sample": sample,
                        "seconds": round(time.monotonic() - t0, 1)})
    for name, url, parse in (
            ("afx.kwayisi.org", "https://afx.kwayisi.org/nse/scom.html", _parse_afx_html),
            ("live.mystocks.co.ke", "https://live.mystocks.co.ke/stock=SCOM", _parse_mystocks_html)):
        t0 = time.monotonic()
        html, err = _get_ex(url, attempts=1)
        parsed = parse(html) if html else {}
        detail = (f"reachable, read SCOM price {parsed['price']}" if parsed.get("price") else
                  "reachable but nothing readable (site layout changed, or quote is not current)" if html else
                  str(err))
        sources.append({"source": name, "kind": "per-stock fallback", "ok": bool(parsed.get("price")),
                        "rows": 1 if parsed else 0, "detail": detail,
                        "sample": {"SCOM": parsed["price"]} if parsed.get("price") else {},
                        "seconds": round(time.monotonic() - t0, 1)})
    good_bulk = sum(1 for x in sources if x["kind"] == "bulk" and x["ok"])
    verdict = "ready" if good_bulk >= 2 else "degraded" if good_bulk == 1 else "blocked"
    advice = {
        "ready": "Automatic updates will work and prices are cross-checked by two sources.",
        "degraded": "Automatic updates will work, but from one bulk source only (no cross-check). "
                    "Look over the numbers, or confirm with Paste prices.",
        "blocked": "This server cannot read any bulk price source. Automatic updates will not bring in "
                   "prices - use Paste prices (or a CSV) from your own browser."}[verdict]
    return {"verdict": verdict, "advice": advice, "market": dict(zip(("state", "trade_date"),
            (market_clock()[0], market_clock()[1].isoformat()))), "sources": sources}


def diagnose() -> None:
    """Command-line version of check_sources()."""
    r = check_sources()
    for x in r["sources"]:
        print(f"{x['source']:20}: {'OK ' if x['ok'] else 'FAIL'} {x['detail']} ({x['seconds']}s)")
    print(f"\nVERDICT: {r['verdict'].upper()} - {r['advice']}")


if __name__ == "__main__":
    diagnose()
