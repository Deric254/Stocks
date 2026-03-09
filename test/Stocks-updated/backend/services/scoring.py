"""
scoring.py — 60-point objective scoring engine (per spec).

Six categories, each 0–10:
  1. Profitability  (0–10)
  2. Dividends      (0–10)
  3. Growth         (0–10)
  4. Value          (0–10)
  5. Asset Safety   (0–10)
  6. Debt Safety    (0–10)

Total: 0–60
  50–60 → Strong Buy
  40–49 → Buy
  30–39 → Hold
  20–29 → Weak
  <20   → Avoid
"""

import math
import pandas as pd


def _safe(val, default=0.0) -> float:
    if val is None:
        return default
    try:
        f = float(val)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return default


def _cagr(start_val: float, end_val: float, years: int) -> float:
    if start_val <= 0 or years <= 0:
        return 0.0
    try:
        return (end_val / start_val) ** (1.0 / years) - 1.0
    except Exception:
        return 0.0


# ── 1. PROFITABILITY (0–10) ───────────────────────────────────────────────────

def _profitability_score(fund: dict) -> dict:
    ni_history = fund.get("net_income_history", [])
    roe = _safe(fund.get("roe"))

    if len(ni_history) >= 2:
        increases = sum(
            1 for i in range(1, len(ni_history))
            if _safe(ni_history[i]) > _safe(ni_history[i - 1])
        )
        if increases >= 4:
            trend_score = 5
        elif increases >= 3:
            trend_score = 3
        else:
            trend_score = 0
    else:
        trend_score = 0

    if roe > 0.15:
        roe_score = 5
    elif roe >= 0.10:
        roe_score = 3
    else:
        roe_score = 1

    total = trend_score + roe_score
    return {
        "profitability_score": total,
        "_profitability_detail": {
            "trend": trend_score,
            "roe": roe_score,
            "roe_value": round(roe * 100, 1),
        }
    }


# ── 2. DIVIDENDS (0–10) ───────────────────────────────────────────────────────

def _dividend_score(fund: dict) -> dict:
    dps_history = fund.get("dps_history", [])
    net_income = _safe(fund.get("net_income"))
    total_divs = _safe(fund.get("total_dividends"))

    years_paid = sum(1 for d in dps_history if _safe(d) > 0)
    if years_paid >= 5:
        consistency_score = 5
    elif years_paid >= 3:
        consistency_score = 3
    else:
        consistency_score = 0

    if net_income > 0:
        payout = total_divs / net_income
    else:
        payout = 0.0

    if 0.30 <= payout <= 0.60:
        payout_score = 5
    elif payout < 0.30 or (0.60 < payout <= 0.80):
        payout_score = 2
    else:
        payout_score = 0

    total = consistency_score + payout_score
    return {
        "dividend_score": total,
        "_dividend_detail": {
            "consistency": consistency_score,
            "payout": payout_score,
            "payout_ratio": round(payout * 100, 1),
            "years_paid": years_paid,
        }
    }


# ── 3. GROWTH (0–10) ─────────────────────────────────────────────────────────

def _growth_score(fund: dict) -> dict:
    rev_history = fund.get("revenue_history", [])
    ni_history = fund.get("net_income_history", [])

    if len(rev_history) >= 2:
        start_rev = _safe(rev_history[0])
        end_rev = _safe(rev_history[-1])
        years = len(rev_history) - 1
        rev_cagr = _cagr(start_rev, end_rev, years)
    else:
        rev_cagr = 0.0

    if rev_cagr > 0.10:
        rev_score = 5
    elif rev_cagr >= 0.05:
        rev_score = 3
    else:
        rev_score = 1

    if len(ni_history) >= 2:
        start_ni = _safe(ni_history[0])
        end_ni = _safe(ni_history[-1])
        years = len(ni_history) - 1
        earn_cagr = _cagr(abs(start_ni) if start_ni != 0 else 1, abs(end_ni), years)
        if start_ni < 0:
            earn_cagr = 0.0
    else:
        earn_cagr = 0.0

    if earn_cagr > 0.10:
        earn_score = 5
    elif earn_cagr >= 0.05:
        earn_score = 3
    else:
        earn_score = 1

    total = rev_score + earn_score
    return {
        "growth_score": total,
        "_growth_detail": {
            "rev_cagr": round(rev_cagr * 100, 1),
            "earn_cagr": round(earn_cagr * 100, 1),
            "rev_score": rev_score,
            "earn_score": earn_score,
        }
    }


# ── 4. VALUE (0–10) ──────────────────────────────────────────────────────────

def _value_score(fund: dict) -> dict:
    pb = _safe(fund.get("pb"), 99.0)
    pe = _safe(fund.get("pe"), 99.0)

    if pb < 1.0:
        pb_score = 5
    elif pb <= 1.5:
        pb_score = 3
    else:
        pb_score = 0

    if pe < 6.0:
        pe_score = 5
    elif pe <= 10.0:
        pe_score = 3
    else:
        pe_score = 0

    total = pb_score + pe_score
    return {
        "value_score": total,
        "_value_detail": {
            "pb": round(pb, 2),
            "pe": round(pe, 2),
            "pb_score": pb_score,
            "pe_score": pe_score,
        }
    }


# ── 5. ASSET SAFETY (0–10) ────────────────────────────────────────────────────

def _asset_safety_score(fund: dict) -> dict:
    eps = _safe(fund.get("eps"))
    price = _safe(fund.get("price"), 1.0)
    total_assets = _safe(fund.get("total_assets"))
    market_cap = _safe(fund.get("market_cap"), 1.0)

    ey = eps / price if price > 0 else 0.0
    if ey > 0.15:
        ey_score = 5
    elif ey >= 0.10:
        ey_score = 3
    else:
        ey_score = 0

    ac = total_assets / market_cap if market_cap > 0 else 0.0
    if ac > 2.0:
        ac_score = 5
    elif ac >= 1.0:
        ac_score = 3
    else:
        ac_score = 0

    total = ey_score + ac_score
    return {
        "asset_safety_score": total,
        "_asset_safety_detail": {
            "earnings_yield": round(ey * 100, 1),
            "asset_coverage": round(ac, 2),
            "ey_score": ey_score,
            "ac_score": ac_score,
        }
    }


# ── 6. DEBT SAFETY (0–10) ────────────────────────────────────────────────────

def _debt_safety_score(fund: dict) -> dict:
    de = _safe(fund.get("debt_to_equity"), 999.0)
    icr = _safe(fund.get("interest_coverage"), 0.0)

    if de < 0.5:
        de_score = 5
    elif de <= 1.0:
        de_score = 3
    else:
        de_score = 0

    if icr > 5.0:
        icr_score = 5
    elif icr >= 2.0:
        icr_score = 3
    else:
        icr_score = 0

    total = de_score + icr_score
    return {
        "debt_safety_score": total,
        "_debt_safety_detail": {
            "de_ratio": round(de, 2),
            "icr": round(icr, 2),
            "de_score": de_score,
            "icr_score": icr_score,
        }
    }


# ── Score label & color ───────────────────────────────────────────────────────

def score_label(total: int) -> str:
    if total >= 50:
        return "Strong Buy"
    elif total >= 40:
        return "Buy"
    elif total >= 30:
        return "Hold"
    elif total >= 20:
        return "Weak"
    else:
        return "Avoid"


def score_color(total: int) -> str:
    if total >= 50:
        return "#49A078"
    elif total >= 40:
        return "#86efac"
    elif total >= 30:
        return "#facc15"
    elif total >= 20:
        return "#f97316"
    else:
        return "#ef4444"


# ── Public interface ──────────────────────────────────────────────────────────

class ScoringEngine:

    def compute_scores(self, prices, fund: dict) -> dict:
        if prices is not None and hasattr(prices, 'empty') and not prices.empty:
            fund = dict(fund)
            fund["price"] = float(prices["close"].iloc[-1])

        r1 = _profitability_score(fund)
        r2 = _dividend_score(fund)
        r3 = _growth_score(fund)
        r4 = _value_score(fund)
        r5 = _asset_safety_score(fund)
        r6 = _debt_safety_score(fund)

        total = (
            r1["profitability_score"] +
            r2["dividend_score"] +
            r3["growth_score"] +
            r4["value_score"] +
            r5["asset_safety_score"] +
            r6["debt_safety_score"]
        )

        normalised = round(total / 60 * 100, 1)

        return {
            "profitability_score": r1["profitability_score"],
            "dividend_score":      r2["dividend_score"],
            "growth_score":        r3["growth_score"],
            "value_score":         r4["value_score"],
            "asset_safety_score":  r5["asset_safety_score"],
            "debt_safety_score":   r6["debt_safety_score"],
            "total_score":         total,
            "label":               score_label(total),
            "color":               score_color(total),
            "detail": {
                "profitability": r1["_profitability_detail"],
                "dividend":      r2["_dividend_detail"],
                "growth":        r3["_growth_detail"],
                "value":         r4["_value_detail"],
                "asset_safety":  r5["_asset_safety_detail"],
                "debt_safety":   r6["_debt_safety_detail"],
            },
            # Legacy keys for backward compat
            "daily":     normalised,
            "monthly":   normalised,
            "long_term": normalised,
            "best_pick": normalised,
        }
