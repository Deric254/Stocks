"""
valuation.py — Layer 6 extension: intrinsic value models.

Existing scoring.py already scores P/E and P/B inside the 0-10 "Value"
category. This module adds the deeper valuation layer the constitution
calls for — DCF, Dividend Discount Model, and margin of safety — as an
ADDITIVE output. It does not change scoring.py's point totals; it
produces a separate "valuation" block the AI Recommendation Engine
(Layer 10, future) and frontend can use.

All models are simple and transparent on purpose (per "no black-box
outputs" / "every calculation must be reproducible"): assumptions are
explicit inputs with sane defaults, and every output states which
assumptions were used.
"""

import math


def _safe(val, default=None):
    if val is None:
        return default
    try:
        f = float(val)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return default


def _cagr(values: list) -> float:
    """CAGR from a chronological list of values (oldest -> newest)."""
    clean = [v for v in values if _safe(v) is not None]
    if len(clean) < 2 or clean[0] <= 0:
        return 0.0
    years = len(clean) - 1
    try:
        return (clean[-1] / clean[0]) ** (1.0 / years) - 1.0
    except Exception:
        return 0.0


# ── DCF (simplified Free-Cash-Flow-to-Equity proxy via net income) ──────

def dcf_valuation(fundamentals: dict, discount_rate: float = 0.14,
                   terminal_growth: float = 0.04, projection_years: int = 5) -> dict:
    """
    Simplified DCF using net income as a FCF proxy (this codebase doesn't
    track separate cash-flow-statement data yet). Discount rate defaults
    to a Kenya-equity-appropriate ~14% (risk-free ~13% T-bond + modest
    equity premium) — explicit so it's auditable, not hidden.
    """
    ni_history = fundamentals.get("net_income_history", [])
    shares = _safe(fundamentals.get("shares_outstanding"))
    market_cap = _safe(fundamentals.get("market_cap"))
    price = _safe(fundamentals.get("price")) or _safe(fundamentals.get("eps"))

    clean_ni = [v for v in ni_history if _safe(v) is not None]
    if len(clean_ni) < 2 or clean_ni[-1] <= 0:
        return {
            "available": False,
            "reason": "Need 2+ years of positive net income history for a DCF estimate",
        }

    growth = _cagr(clean_ni)
    growth = max(min(growth, 0.25), -0.10)

    base = clean_ni[-1]
    pv_sum = 0.0
    projected = []
    cf = base
    for yr in range(1, projection_years + 1):
        cf = cf * (1 + growth)
        pv = cf / ((1 + discount_rate) ** yr)
        pv_sum += pv
        projected.append(round(cf, 2))

    terminal_value = (cf * (1 + terminal_growth)) / (discount_rate - terminal_growth)
    pv_terminal = terminal_value / ((1 + discount_rate) ** projection_years)

    enterprise_value = pv_sum + pv_terminal

    fair_value_per_share = None
    if shares and shares > 0:
        fair_value_per_share = enterprise_value / shares
    elif market_cap and market_cap > 0 and price:
        implied_shares = market_cap / price
        if implied_shares > 0:
            fair_value_per_share = enterprise_value / implied_shares

    result = {
        "available": True,
        "assumptions": {
            "discount_rate": discount_rate,
            "terminal_growth": terminal_growth,
            "projection_years": projection_years,
            "historical_growth_used": round(growth, 4),
        },
        "projected_cash_flows": projected,
        "pv_of_projections": round(pv_sum, 2),
        "pv_of_terminal_value": round(pv_terminal, 2),
        "intrinsic_value_total": round(enterprise_value, 2),
        "fair_value_per_share": round(fair_value_per_share, 2) if fair_value_per_share else None,
    }

    if fair_value_per_share and price:
        upside = (fair_value_per_share - price) / price
        result["current_price"] = round(price, 2)
        result["upside_pct"] = round(upside * 100, 1)
        result["verdict"] = (
            "Undervalued" if upside > 0.15 else
            "Overvalued" if upside < -0.15 else
            "Fairly Valued"
        )

    return result


# ── Dividend Discount Model (Gordon Growth) ──────────────────────────────

def ddm_valuation(fundamentals: dict, required_return: float = 0.12) -> dict:
    dps_history = fundamentals.get("dps_history", [])
    price = _safe(fundamentals.get("price")) or None
    clean_dps = [v for v in dps_history if _safe(v) is not None]

    if not clean_dps or clean_dps[-1] is None or clean_dps[-1] <= 0:
        return {"available": False, "reason": "No positive dividend history — DDM not applicable"}

    last_dps = clean_dps[-1]
    growth = _cagr(clean_dps) if len(clean_dps) >= 2 else 0.0
    growth = max(min(growth, 0.15), -0.05)

    if required_return <= growth:
        return {
            "available": False,
            "reason": "Required return must exceed dividend growth rate for Gordon Growth to apply",
        }

    next_dps = last_dps * (1 + growth)
    fair_value = next_dps / (required_return - growth)

    result = {
        "available": True,
        "assumptions": {
            "required_return": required_return,
            "dividend_growth_used": round(growth, 4),
            "last_dps": round(last_dps, 4),
        },
        "fair_value_per_share": round(fair_value, 2),
    }
    if price:
        upside = (fair_value - price) / price
        result["current_price"] = round(price, 2)
        result["upside_pct"] = round(upside * 100, 1)
        result["verdict"] = (
            "Undervalued" if upside > 0.15 else
            "Overvalued" if upside < -0.15 else
            "Fairly Valued"
        )
    return result


# ── Historical valuation bands (where current P/E and P/B sit) ──────────

def valuation_bands(fundamentals: dict) -> dict:
    """
    Without a stored multi-year multiples history, this approximates
    bands from current fundamentals only — flagged clearly so it's
    never mistaken for a true historical P/E/P-B band time series.
    """
    eps = _safe(fundamentals.get("eps"))
    bvps = _safe(fundamentals.get("bvps"))
    price = _safe(fundamentals.get("price"))
    pe = _safe(fundamentals.get("pe"))
    pb = _safe(fundamentals.get("pb"))

    if not price or (not eps and not bvps):
        return {"available": False, "reason": "Insufficient price/EPS/BVPS data"}

    return {
        "available": True,
        "current_pe": round(pe, 2) if pe else None,
        "current_pb": round(pb, 2) if pb else None,
        "note": (
            "Approximated from latest fundamentals only — true historical "
            "P/E and P/B bands require stored quarterly multiples history, "
            "not yet tracked by this system."
        ),
    }


def margin_of_safety(fair_values: list, price) -> dict:
    """
    Aggregates fair-value estimates from multiple models (DCF, DDM, etc.)
    into a single margin-of-safety figure, per the constitution's
    requirement that valuation output include explicit MoS.
    """
    clean = [v for v in fair_values if v is not None and v > 0]
    price = _safe(price)
    if not clean or not price:
        return {"available": False, "reason": "Need at least one valid fair-value estimate and current price"}

    avg_fair_value = sum(clean) / len(clean)
    mos = (avg_fair_value - price) / avg_fair_value

    return {
        "available": True,
        "models_used": len(clean),
        "average_fair_value": round(avg_fair_value, 2),
        "current_price": round(price, 2),
        "margin_of_safety_pct": round(mos * 100, 1),
        "confidence": "Medium" if len(clean) >= 2 else "Low",
    }


def compute_valuation(fundamentals: dict) -> dict:
    """Main entry point — runs all models and aggregates."""
    dcf = dcf_valuation(fundamentals)
    ddm = ddm_valuation(fundamentals)
    bands = valuation_bands(fundamentals)

    fair_values = []
    if dcf.get("available") and dcf.get("fair_value_per_share"):
        fair_values.append(dcf["fair_value_per_share"])
    if ddm.get("available") and ddm.get("fair_value_per_share"):
        fair_values.append(ddm["fair_value_per_share"])

    price = _safe(fundamentals.get("price"))
    mos = margin_of_safety(fair_values, price)

    return {
        "dcf": dcf,
        "ddm": ddm,
        "valuation_bands": bands,
        "margin_of_safety": mos,
    }
