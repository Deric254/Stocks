"""
macro.py — Layer 1: Global Intelligence Engine.

Determines where global capital is likely to flow, using two free
data sources:

  FRED (St. Louis Fed)  — interest rates, inflation, GDP, PMI, yield
                           curve, money supply, housing, employment,
                           consumer confidence. REQUIRES a free API
                           key (fred.stlouisfed.org/docs/api/api_key.html)
                           set as the FRED_API_KEY environment variable.
                           Degrades gracefully (clearly labeled
                           "not configured") if the key is absent —
                           this is intentional per product decision,
                           not a bug.

  stooq.com             — DXY proxy, VIX, gold, oil, copper, natural
                           gas daily closes. No key required. Free CSV
                           endpoint, no rate-limit documented but kept
                           polite (cached, not hammered).

Every value returned carries {value, source, timestamp, confidence}
so the explainability layer (constitution: "every dataset must
include source/timestamp/confidence") can trace it.

NOTE: this module makes live HTTP calls to api.stlouisfed.org and
stooq.com. It has NOT been exercised against live endpoints in the
build/test sandbox (network there is locked to package registries
only) — logic has been unit-verified against mocked responses only.
Run a live smoke test (`compute_global_intelligence()`) on first
deploy with real network access before trusting it in production.
"""

import os
import time
import requests
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from services.stooq_client import fetch_stooq_closes

FRED_API_KEY = os.environ.get("FRED_API_KEY", "").strip()
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
STOOQ_BASE = "https://stooq.com/q/d/l/"

_CACHE = {}
_CACHE_TTL_SECONDS = 3600  # 1 hour — macro data doesn't move intraday


def _cache_get(key):
    entry = _CACHE.get(key)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL_SECONDS:
        return entry["value"]
    return None


def _cache_set(key, value):
    _CACHE[key] = {"value": value, "ts": time.time()}


def _wrap(value, source, confidence="High", note=None):
    return {
        "value": value,
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "confidence": confidence,
        "note": note,
    }


def _unavailable(reason, source):
    return {
        "value": None,
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "confidence": "None",
        "note": reason,
    }


# ── FRED ───────────────────────────────────────────────────────────────

# series_id -> (human label, units note)
FRED_SERIES = {
    "DFF":       ("Federal Funds Rate", "% — daily"),
    "CPIAUCSL":  ("CPI (Inflation, YoY basis requires calc)", "index"),
    "GDP":       ("US GDP", "$ billions, quarterly"),
    "UNRATE":    ("Unemployment Rate", "%"),
    "T10Y2Y":    ("10Y-2Y Treasury Yield Spread", "% — yield curve"),
    "M2SL":      ("M2 Money Supply", "$ billions"),
    "HOUST":     ("Housing Starts", "thousands, annualized"),
    "UMCSENT":   ("Consumer Sentiment (U. Michigan)", "index"),
    # NOTE: FRED's old ISM Manufacturing PMI series ("NAPM") was
    # discontinued around 2016 when the Fed stopped redistributing
    # ISM's proprietary data — that series ID will always fail now,
    # not a bug in this code. INDPRO (Industrial Production Index) is
    # a genuine, currently-active free substitute for manufacturing/
    # industrial activity, but it's an output-level index (base ~100),
    # NOT a diffusion index like PMI — there's no "50 = expansion"
    # threshold for it. Honestly labeled as a substitute, not the
    # literal ISM PMI, since no free equivalent of the real thing
    # exists — see _classify_regime() for how it's actually used
    # (year-over-year direction, not an absolute level).
    "INDPRO":    ("Industrial Production Index (PMI substitute - no free ISM PMI exists)", "index, base ~100"),
}


def _fetch_fred_series(series_id: str, limit: int = 13):
    """Fetch the most recent `limit` observations for a FRED series.
    Returns list of (date, value) oldest->newest, or None if unavailable."""
    if not FRED_API_KEY:
        return None

    cache_key = f"fred:{series_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = requests.get(FRED_BASE, params={
            "series_id": series_id,
            "api_key": FRED_API_KEY,
            "file_type": "json",
            "sort_order": "desc",
            "limit": limit,
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        obs = data.get("observations", [])
        clean = [(o["date"], float(o["value"])) for o in obs if o.get("value") not in (".", None)]
        clean.reverse()  # oldest -> newest
        _cache_set(cache_key, clean)
        return clean
    except Exception:
        return None


def get_fred_indicator(series_id: str) -> dict:
    if series_id not in FRED_SERIES:
        return _unavailable(f"Unknown FRED series '{series_id}'", "FRED")
    if not FRED_API_KEY:
        return _unavailable(
            "FRED_API_KEY not configured — set the environment variable to enable this indicator",
            "FRED (not configured)",
        )

    label, units = FRED_SERIES[series_id]
    history = _fetch_fred_series(series_id)
    if not history:
        return _unavailable(f"FRED fetch failed or returned no data for {series_id}", "FRED")

    latest_date, latest_val = history[-1]
    yoy_change = None
    if len(history) >= 13:
        year_ago_val = history[0][1]
        if year_ago_val:
            yoy_change = round((latest_val - year_ago_val) / abs(year_ago_val) * 100, 2)

    return {
        "value": round(latest_val, 3),
        "label": label,
        "units": units,
        "as_of": latest_date,
        "yoy_change_pct": yoy_change,
        "source": "FRED (St. Louis Fed)",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "confidence": "High",
    }


# ── stooq (keyless daily CSV, via shared stooq_client) ───────────────

STOOQ_SYMBOLS = {
    "dxy_proxy":   "uup.us",     # USD bull ETF as a DXY proxy (true DXY index not free on stooq)
    "vix":         "^vix",
    "gold":        "xauusd",
    "silver":      "xagusd",
    "oil_wti":     "cl.f",
    "natural_gas": "ng.f",
    "copper":      "hg.f",
}


def get_commodity_or_index(key: str) -> dict:
    if key not in STOOQ_SYMBOLS:
        return _unavailable(f"Unknown symbol key '{key}'", "stooq")

    symbol = STOOQ_SYMBOLS[key]
    history = fetch_stooq_closes(symbol, days=30)
    if not history:
        return _unavailable(f"stooq fetch failed for {symbol}", "stooq")

    latest_date, latest_val = history[-1]
    change_30d_pct = None
    if len(history) >= 2:
        first_val = history[0][1]
        if first_val:
            change_30d_pct = round((latest_val - first_val) / first_val * 100, 2)

    return {
        "value": round(latest_val, 4),
        "as_of": latest_date,
        "change_30d_pct": change_30d_pct,
        "source": f"stooq.com ({symbol})",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "confidence": "Medium",  # ETF/futures proxies, not the canonical index in some cases
    }


# ── Composite Global scores ───────────────────────────────────────────

def _classify_regime(fed_funds, cpi_yoy, yield_curve, industrial_yoy) -> str:
    """Simple, transparent rule-based regime classification —
    deliberately not a black box per constitution Layer 10 requirement.
    industrial_yoy: year-over-year % change in industrial production,
    used as a manufacturing-activity direction signal since no free
    ISM-PMI-equivalent (diffusion index, 50 = expansion line) exists —
    see FRED_SERIES['INDPRO'] comment for why."""
    signals = []
    if yield_curve is not None:
        signals.append("inverted_curve" if yield_curve < 0 else "normal_curve")
    if industrial_yoy is not None:
        signals.append("expansion" if industrial_yoy >= 0 else "contraction")
    if cpi_yoy is not None:
        signals.append("high_inflation" if cpi_yoy > 4 else ("low_inflation" if cpi_yoy < 2 else "moderate_inflation"))

    if "inverted_curve" in signals and "contraction" in signals:
        return "Late Cycle / Slowdown Risk"
    if "expansion" in signals and "low_inflation" in signals:
        return "Early-to-Mid Cycle Expansion"
    if "expansion" in signals and "high_inflation" in signals:
        return "Late Cycle / Overheating"
    if "contraction" in signals:
        return "Contraction / Recession Risk"
    if not signals:
        return "Unknown — insufficient indicator coverage"
    return "Mid-Cycle / Mixed Signals"


def compute_global_intelligence() -> dict:
    """Main entry point — Layer 1 output. Fetches all FRED series and
    all stooq symbols concurrently (was sequential — up to 16 blocking
    HTTP calls in series, now bounded by the slowest single call)."""
    with ThreadPoolExecutor(max_workers=16) as ex:
        fred_futures = {sid: ex.submit(get_fred_indicator, sid) for sid in FRED_SERIES}
        market_futures = {key: ex.submit(get_commodity_or_index, key) for key in STOOQ_SYMBOLS}
        indicators = {sid: f.result() for sid, f in fred_futures.items()}
        market = {key: f.result() for key, f in market_futures.items()}

    fred_configured = bool(FRED_API_KEY)
    available_fred = [v for v in indicators.values() if v.get("value") is not None]
    available_market = [v for v in market.values() if v.get("value") is not None]

    fed_funds = indicators["DFF"].get("value")
    cpi_yoy = indicators["CPIAUCSL"].get("yoy_change_pct")
    yield_curve = indicators["T10Y2Y"].get("value")
    industrial_yoy = indicators["INDPRO"].get("yoy_change_pct")

    regime = _classify_regime(fed_funds, cpi_yoy, yield_curve, industrial_yoy)

    vix_val = market["vix"].get("value")
    risk_score = None
    if vix_val is not None:
        # VIX < 15 = low risk/complacent, 15-25 = normal, >25 = elevated, >35 = crisis
        risk_score = round(min(max((vix_val - 10) / 30, 0), 1) * 100, 1)

    return {
        "available": fred_configured or bool(available_market),
        "fred_configured": fred_configured,
        "fred_coverage": f"{len(available_fred)}/{len(FRED_SERIES)} indicators" if fred_configured else "Not configured (set FRED_API_KEY)",
        "indicators": indicators,
        "market_signals": market,
        "economic_regime": regime,
        "global_risk_score": risk_score,
        "global_risk_score_note": "Derived from VIX (10=calm floor, 40=crisis ceiling, scaled 0-100). Approximation, not a formal risk model.",
        "data_quality_warning": (
            None if fred_configured else
            "FRED_API_KEY not set — global rates/inflation/GDP/PMI indicators unavailable. "
            "Market signals (VIX, gold, oil, etc. via stooq) still work without a key."
        ),
    }
