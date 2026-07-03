"""
country.py — Layer 2: Country Intelligence Engine.

Uses the World Bank API (api.worldbank.org), which is free and
requires no API key. Covers GDP growth, inflation, unemployment,
current account balance, and foreign direct investment — the World
Bank doesn't reliably publish credit ratings or real-time political
stability indices for free, so those constitution fields are marked
unavailable rather than faked.

NOTE: like macro.py, this has NOT been exercised against the live
World Bank endpoint in the build sandbox (no network access there).
Logic is unit-verified against mocked response shapes only — run a
live smoke test on first deploy.
"""

import time
import requests
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

WB_BASE = "https://api.worldbank.org/v2/country"

# World Bank 3-letter country codes relevant to an NSE-focused platform,
# plus major global economies for capital-flow context.
DEFAULT_COUNTRIES = {
    "KEN": "Kenya",
    "USA": "United States",
    "GBR": "United Kingdom",
    "CHN": "China",
    "ZAF": "South Africa",
    "NGA": "Nigeria",
    "IND": "India",
}

# indicator_code -> (label, units)
WB_INDICATORS = {
    "NY.GDP.MKTP.KD.ZG":    ("GDP Growth", "% annual"),
    "FP.CPI.TOTL.ZG":       ("Inflation (CPI)", "% annual"),
    "SL.UEM.TOTL.ZS":       ("Unemployment Rate", "% of labor force"),
    "BN.CAB.XOKA.GD.ZS":    ("Current Account Balance", "% of GDP"),
    "BX.KLT.DINV.WD.GD.ZS": ("Foreign Direct Investment (net inflows)", "% of GDP"),
    "GC.DOD.TOTL.GD.ZS":    ("Central Government Debt", "% of GDP"),
}

_CACHE = {}
_CACHE_TTL_SECONDS = 86400  # 24h — World Bank data updates annually/quarterly at most


def _cache_get(key):
    entry = _CACHE.get(key)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL_SECONDS:
        return entry["value"]
    return None


def _cache_set(key, value):
    _CACHE[key] = {"value": value, "ts": time.time()}


def _fetch_indicator(country_code: str, indicator_code: str):
    """Returns most recent (year, value) pair, or None."""
    cache_key = f"{country_code}:{indicator_code}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        url = f"{WB_BASE}/{country_code}/indicator/{indicator_code}"
        resp = requests.get(url, params={
            "format": "json",
            "per_page": 10,
            "mrnev": 5,  # most recent non-empty values
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or len(data) < 2 or not data[1]:
            return None
        rows = [(r["date"], r["value"]) for r in data[1] if r.get("value") is not None]
        if not rows:
            return None
        rows.sort(key=lambda r: r[0])
        result = rows[-1]
        _cache_set(cache_key, result)
        return result
    except Exception:
        return None


def get_country_indicator(country_code: str, indicator_code: str) -> dict:
    if indicator_code not in WB_INDICATORS:
        return {"value": None, "note": f"Unknown indicator '{indicator_code}'"}

    label, units = WB_INDICATORS[indicator_code]
    result = _fetch_indicator(country_code, indicator_code)

    if result is None:
        return {
            "value": None, "label": label, "units": units,
            "source": "World Bank", "confidence": "None",
            "note": "Fetch failed or no data published for this country/indicator",
        }

    year, value = result
    return {
        "value": round(float(value), 3),
        "label": label,
        "units": units,
        "as_of_year": year,
        "source": "World Bank",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "confidence": "High",
    }


def _country_score(indicators: dict) -> dict:
    """0-100 composite, transparent and reproducible. Missing
    indicators reduce coverage/confidence rather than defaulting to 0
    (per constitution: 'missing values must never silently influence
    recommendations')."""
    weights = {
        "NY.GDP.MKTP.KD.ZG":    (0.30, lambda v: min(max(v, -5), 8) / 8),               # higher growth = better
        "FP.CPI.TOTL.ZG":       (0.20, lambda v: 1 - min(abs(v - 2.5), 10) / 10),       # closer to ~2.5% target = better
        "SL.UEM.TOTL.ZS":       (0.20, lambda v: 1 - min(v, 25) / 25),                  # lower unemployment = better
        "BN.CAB.XOKA.GD.ZS":    (0.15, lambda v: min(max(v, -10), 10) / 10 / 2 + 0.5),  # closer to balanced/surplus = better
        "BX.KLT.DINV.WD.GD.ZS": (0.15, lambda v: min(max(v, 0), 10) / 10),              # more FDI inflow = better
    }

    score = 0.0
    weight_used = 0.0
    for code, (weight, fn) in weights.items():
        ind = indicators.get(code, {})
        val = ind.get("value")
        if val is None:
            continue
        try:
            normalized = max(0, min(1, fn(val)))
        except Exception:
            continue
        score += normalized * weight
        weight_used += weight

    total_possible_weight = sum(w for w, _ in weights.values())
    if weight_used == 0:
        return {"score": None, "confidence": "None", "coverage": f"0/{len(weights)} indicators"}

    final_score = round((score / weight_used) * 100, 1)
    confidence = "High" if weight_used >= 0.75 else ("Medium" if weight_used >= 0.4 else "Low")
    covered_count = round(weight_used / total_possible_weight * len(weights))

    return {
        "score": final_score,
        "confidence": confidence,
        "coverage": f"{covered_count}/{len(weights)} indicators",
    }


def get_country_profile(country_code: str) -> dict:
    country_code = country_code.upper()
    name = DEFAULT_COUNTRIES.get(country_code, country_code)
    with ThreadPoolExecutor(max_workers=len(WB_INDICATORS)) as ex:
        futures = {code: ex.submit(get_country_indicator, country_code, code) for code in WB_INDICATORS}
        indicators = {code: f.result() for code, f in futures.items()}
    score = _country_score(indicators)

    outlook = "Unknown"
    if score["score"] is not None:
        s = score["score"]
        outlook = "Attractive" if s >= 65 else "Favorable" if s >= 50 else "Mixed" if s >= 35 else "Caution"

    return {
        "country_code": country_code,
        "country_name": name,
        "indicators": indicators,
        "country_score": score,
        "outlook": outlook,
        "note": (
            "Credit rating and political stability indices are not available "
            "from free World Bank data — those constitution fields remain "
            "unavailable until a paid source (e.g. Moody's, S&P) is added."
        ),
    }


def compute_country_intelligence(country_codes: list = None) -> dict:
    """Main entry point — Layer 2 output across all tracked countries.
    Every (country, indicator) pair is fetched concurrently — was up to
    6 indicators x 7 countries = 42 sequential blocking HTTP calls,
    now bounded by the slowest single call."""
    codes = country_codes or list(DEFAULT_COUNTRIES.keys())
    all_pairs = [(code, ind) for code in codes for ind in WB_INDICATORS]

    with ThreadPoolExecutor(max_workers=min(len(all_pairs) or 1, 24)) as ex:
        futures = {(code, ind): ex.submit(get_country_indicator, code, ind) for code, ind in all_pairs}
        results = {pair: f.result() for pair, f in futures.items()}

    profiles = {}
    for code in codes:
        name = DEFAULT_COUNTRIES.get(code, code)
        indicators = {ind: results[(code, ind)] for ind in WB_INDICATORS}
        score = _country_score(indicators)
        outlook = "Unknown"
        if score["score"] is not None:
            s = score["score"]
            outlook = "Attractive" if s >= 65 else "Favorable" if s >= 50 else "Mixed" if s >= 35 else "Caution"
        profiles[code] = {
            "country_code": code,
            "country_name": name,
            "indicators": indicators,
            "country_score": score,
            "outlook": outlook,
            "note": (
                "Credit rating and political stability indices are not available "
                "from free World Bank data — those constitution fields remain "
                "unavailable until a paid source (e.g. Moody's, S&P) is added."
            ),
        }

    ranked = sorted(
        [p for p in profiles.values() if p["country_score"]["score"] is not None],
        key=lambda p: p["country_score"]["score"],
        reverse=True,
    )

    return {
        "available": any(p["country_score"]["score"] is not None for p in profiles.values()),
        "countries": profiles,
        "ranked_by_score": [{"country_code": p["country_code"], "country_name": p["country_name"],
                              "score": p["country_score"]["score"]} for p in ranked],
    }
