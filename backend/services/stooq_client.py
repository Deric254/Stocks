"""
stooq_client.py — shared keyless stooq.com CSV client.

Extracted because the exact same fetch/parse/cache logic was
duplicated in macro.py and sector.py. Single source of truth now.
"""

import time
import requests

STOOQ_BASE = "https://stooq.com/q/d/l/"

# Some sites (stooq included) apply basic bot detection against the
# default "python-requests/x.x" User-Agent string that the requests
# library sends otherwise. A realistic browser UA is a common,
# low-risk fix for requests that fail uniformly across every symbol —
# which is exactly what a User-Agent block looks like (every request
# fails the same way, not just some).
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

_CACHE = {}
_CACHE_TTL_SECONDS = 3600


def _cache_get(key):
    entry = _CACHE.get(key)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL_SECONDS:
        return entry["value"]
    return None


def _cache_set(key, value):
    _CACHE[key] = {"value": value, "ts": time.time()}


def fetch_stooq_closes(symbol: str, days: int = 90):
    """Returns list of (date_str, close_float) oldest->newest, or None on failure."""
    cache_key = f"stooq:{symbol}:{days}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = requests.get(STOOQ_BASE, params={"s": symbol, "i": "d"}, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        lines = resp.text.strip().split("\n")
        if len(lines) < 2 or "Date" not in lines[0]:
            print(f"[stooq] Unexpected response format for symbol '{symbol}': {resp.text[:150]!r}")
            return None
        rows = [l.split(",") for l in lines[1:] if l]
        parsed = [(r[0], float(r[4])) for r in rows if len(r) >= 5 and r[4] not in ("", "N/D")]
        parsed = parsed[-days:]
        _cache_set(cache_key, parsed)
        return parsed
    except Exception as e:
        # Surfaced to stdout (visible in Render logs) rather than
        # silently swallowed — the previous version gave no way to
        # tell WHY a fetch failed (blocked? timeout? bad symbol?
        # changed response format?) without this.
        print(f"[stooq] fetch failed for symbol '{symbol}': {e}")
        return None
