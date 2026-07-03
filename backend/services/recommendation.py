"""
recommendation.py — Layer 10: AI Recommendation Engine.

Combines outputs from scoring.py (Layer 5), valuation.py (Layer 6),
capital_flow.py (Layer 7), technical.py (Layer 8), and sector.py
(Layer 3) into one synthesized, explainable recommendation.

Per the constitution's explicit requirement — "No black-box outputs"
— this is a transparent, rule-based weighted synthesis, not an LLM
call. Every component contributes a stated, visible weight, and every
output names which layers were available vs. missing so the
recommendation's confidence is honest about its own coverage gaps.

A future iteration could route the structured outputs of this module
through an LLM purely for natural-language *prose* polish — that's a
presentation layer on top of this, not a replacement for the
transparent scoring underneath it.
"""

from datetime import datetime, timezone


WEIGHTS = {
    "company": 0.30,       # Layer 5 — fundamentals (existing 60-pt scoring engine)
    "valuation": 0.20,     # Layer 6 — DCF/DDM margin of safety
    "technical": 0.20,     # Layer 8 — trend/momentum
    "capital_flow": 0.15,  # Layer 7 — accumulation/distribution
    "sector": 0.15,        # Layer 3/4 — NSE sector momentum context
}


def _normalize_company(scores: dict):
    total = scores.get("total_score")
    if total is None:
        return None
    return max(0, min(100, (total / 60) * 100))


def _normalize_valuation(valuation: dict):
    mos = valuation.get("margin_of_safety", {})
    if not mos.get("available"):
        return None
    pct = mos["margin_of_safety_pct"]
    return max(0, min(100, (pct + 30) / 60 * 100))


def _normalize_technical(technical: dict):
    ts = technical.get("technical_score", {})
    return ts.get("score")


def _normalize_capital_flow(capital_flow: dict):
    if not capital_flow.get("available"):
        return None
    return capital_flow.get("capital_flow_score")


def _normalize_sector(sector_name: str, nse_sector_data: dict):
    sectors = (nse_sector_data or {}).get("sectors", {})
    d = sectors.get(sector_name)
    if not d or not d.get("available"):
        return None
    momentum = d["avg_momentum_1m_pct"]
    return max(0, min(100, (momentum + 10) / 20 * 100))


def _verdict_label(score: float) -> str:
    if score >= 75:
        return "Strong Buy"
    if score >= 60:
        return "Buy"
    if score >= 45:
        return "Hold"
    if score >= 30:
        return "Reduce"
    return "Avoid"


def _confidence_label(coverage_pct: float) -> str:
    if coverage_pct >= 80:
        return "High"
    if coverage_pct >= 50:
        return "Medium"
    return "Low"


def _build_thesis(ticker: str, name: str, components: dict, overall: float, verdict: str) -> dict:
    supporting = []
    risks = []

    if components.get("company") is not None:
        c = components["company"]
        if c >= 60:
            supporting.append(f"Strong fundamentals — company quality score of {c:.0f}/100")
        elif c < 40:
            risks.append(f"Weak fundamentals — company quality score of only {c:.0f}/100")

    if components.get("valuation") is not None:
        v = components["valuation"]
        if v >= 60:
            supporting.append("Trading below estimated intrinsic value (positive margin of safety)")
        elif v < 40:
            risks.append("Trading above estimated intrinsic value (negative margin of safety)")

    if components.get("technical") is not None:
        t = components["technical"]
        if t >= 60:
            supporting.append("Technical trend and momentum are favorable")
        elif t < 40:
            risks.append("Technical trend and momentum are unfavorable")

    if components.get("capital_flow") is not None:
        cf = components["capital_flow"]
        if cf >= 60:
            supporting.append("Volume signals show accumulation (buying pressure)")
        elif cf < 40:
            risks.append("Volume signals show distribution (selling pressure)")

    if components.get("sector") is not None:
        s = components["sector"]
        if s >= 60:
            supporting.append("Sector has positive recent momentum")
        elif s < 40:
            risks.append("Sector has negative recent momentum — headwind")

    missing = [k for k, v in components.items() if v is None]
    invalidating = []
    if missing:
        invalidating.append(
            f"Recommendation does not account for: {', '.join(missing)} — "
            "data unavailable. Coverage gap, not a negative signal."
        )
    if not supporting and not risks:
        invalidating.append("Insufficient data across all layers to form a meaningful thesis")

    return {
        "summary": f"{ticker} ({name}) scores {overall:.0f}/100 overall — classified as {verdict}.",
        "supporting_evidence": supporting,
        "primary_risks": risks,
        "what_could_invalidate_this": invalidating,
    }


def compute_adaptive_weights(effectiveness: dict, max_adjustment: float = 0.4) -> dict:
    """
    Adjusts the static WEIGHTS based on real historical effectiveness
    (continuous_learning.get_component_effectiveness) — this is what
    makes Layer 12 an actual feedback loop instead of a log nobody
    reads. Only components with 'reliable': True (enough sample size)
    are adjusted; everything else keeps its static weight.

    max_adjustment caps how far any single component's weight can move
    from its default (±40% relative, by default) — a deliberate guard
    against a system used for real capital swinging wildly based on a
    correlation that's still statistically thin. Adjustment direction
    follows the sign and magnitude of the correlation: components that
    have actually predicted returns well get more weight, components
    that haven't get less — but bounded, always.
    """
    component_map = {
        "company": "company_score",
        "valuation": "valuation_score",
        "technical": "technical_score",
        "capital_flow": "capital_flow_score",
        "sector": "sector_score",
    }

    if not effectiveness or not effectiveness.get("components"):
        return {
            "weights": dict(WEIGHTS),
            "adaptive": False,
            "reason": "No effectiveness data available — using static default weights",
        }

    adjusted = dict(WEIGHTS)
    adjustments_applied = {}

    for rec_key, cl_key in component_map.items():
        comp_data = effectiveness["components"].get(cl_key, {})
        if not comp_data.get("reliable"):
            continue
        corr = comp_data.get("correlation")
        if corr is None:
            continue
        # correlation in [-1,1] -> scale factor in [1-max_adj, 1+max_adj]
        scale = 1.0 + max(-1.0, min(1.0, corr)) * max_adjustment
        adjusted[rec_key] = WEIGHTS[rec_key] * scale
        adjustments_applied[rec_key] = {
            "correlation": corr,
            "sample_size": comp_data["sample_size"],
            "static_weight": WEIGHTS[rec_key],
            "adjusted_weight": round(adjusted[rec_key], 4),
        }

    total = sum(adjusted.values())
    if total > 0:
        adjusted = {k: v / total for k, v in adjusted.items()}

    return {
        "weights": adjusted,
        "adaptive": bool(adjustments_applied),
        "adjustments_applied": adjustments_applied,
        "reason": None if adjustments_applied else (
            f"No component has {effectiveness.get('min_samples_required', 20)}+ evaluated "
            "recommendations yet — using static default weights until enough history accumulates"
        ),
    }


def synthesize_recommendation(ticker: str, name: str, sector_name: str,
                               company_scores: dict, valuation: dict,
                               technical: dict, capital_flow: dict,
                               nse_sector_data: dict = None,
                               current_price: float = None,
                               weights: dict = None) -> dict:
    """Main entry point — Layer 10 output for a single stock.
    weights: optional override (e.g. from compute_adaptive_weights) —
    defaults to the static WEIGHTS if not supplied."""
    active_weights = weights or WEIGHTS
    components = {
        "company":      _normalize_company(company_scores or {}),
        "valuation":    _normalize_valuation(valuation or {}),
        "technical":    _normalize_technical(technical or {}),
        "capital_flow": _normalize_capital_flow(capital_flow or {}),
        "sector":       _normalize_sector(sector_name, nse_sector_data),
    }

    weighted_sum = 0.0
    weight_used = 0.0
    for key, value in components.items():
        if value is None:
            continue
        weighted_sum += value * active_weights[key]
        weight_used += active_weights[key]

    if weight_used == 0:
        return {
            "available": False,
            "reason": "No layers had sufficient data to synthesize a recommendation",
            "ticker": ticker,
        }

    overall_score = round(weighted_sum / weight_used, 1)
    coverage_pct = round(weight_used / sum(active_weights.values()) * 100, 1)
    verdict = _verdict_label(overall_score)
    confidence = _confidence_label(coverage_pct)

    thesis = _build_thesis(ticker, name, components, overall_score, verdict)

    return {
        "available": True,
        "ticker": ticker,
        "name": name,
        "overall_score": overall_score,
        "recommendation": verdict,
        "confidence": confidence,
        "coverage_pct": coverage_pct,
        "component_scores": {k: (round(v, 1) if v is not None else None) for k, v in components.items()},
        "component_weights": active_weights,
        "current_price": current_price,
        "thesis": thesis,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methodology_note": (
            "Transparent weighted-average synthesis across available layers — "
            "not an LLM-generated opinion. Every component score is independently "
            "reproducible from the underlying layer's calculation." +
            (" Weights have been adjusted based on historical performance (see /api/recommendations/effectiveness)."
             if weights and weights != WEIGHTS else "")
        ),
    }
