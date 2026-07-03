"""
test_feedback_loop.py — Layer 12 -> Layer 10 adaptive weighting logic.

This is the highest-stakes piece of logic in the codebase: it changes
which numbers drive a "Buy"/"Sell" recommendation based on historical
performance. If it's wrong, it's wrong in a way that's hard to notice
by eyeballing the UI. It gets a dedicated, thorough test file.

Run with: pytest tests/test_feedback_loop.py -v
"""

import os
import sys
import random
import pathlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import services.continuous_learning as cl
from services.recommendation import compute_adaptive_weights, WEIGHTS


def _isolated_cl(tmp_path):
    """Point continuous_learning at a throwaway CSV so tests never
    touch real recommendation history."""
    cl.DATA_DIR = pathlib.Path(tmp_path)
    cl.RECOMMENDATIONS_CSV = cl.DATA_DIR / "recommendations_log.csv"


def test_no_history_does_not_adapt(tmp_path):
    _isolated_cl(tmp_path)
    eff = cl.get_component_effectiveness(min_samples=20)
    adaptive = compute_adaptive_weights(eff)
    assert adaptive["adaptive"] is False
    assert adaptive["weights"] == WEIGHTS


def test_below_min_samples_does_not_adapt(tmp_path):
    _isolated_cl(tmp_path)
    random.seed(1)
    for i in range(5):  # below default min_samples=20
        rec_id = cl.log_recommendation(f"T{i}", {
            "company_score": random.uniform(20, 90), "valuation_score": 50,
            "technical_score": 50, "capital_flow_score": 50, "sector_score": 50,
            "overall_recommendation": "Buy", "confidence": "Medium",
            "price_at_recommendation": 100, "thesis_summary": "test",
        })
        cl.record_outcome(rec_id, 100 + random.uniform(-5, 5))

    eff = cl.get_component_effectiveness(min_samples=20)
    adaptive = compute_adaptive_weights(eff)
    assert adaptive["adaptive"] is False, "must not adapt below min_samples threshold"
    assert adaptive["weights"] == WEIGHTS


def test_strong_correlation_shifts_weight_up(tmp_path):
    _isolated_cl(tmp_path)
    random.seed(42)
    for i in range(30):
        company = random.uniform(20, 90)
        outcome = (company - 50) * 0.6 + random.uniform(-3, 3)  # strong signal
        rec_id = cl.log_recommendation(f"T{i}", {
            "company_score": company,
            "valuation_score": random.uniform(20, 90),  # noise — uncorrelated
            "technical_score": random.uniform(20, 90),
            "capital_flow_score": random.uniform(20, 90),
            "sector_score": random.uniform(20, 90),
            "overall_recommendation": "Buy", "confidence": "Medium",
            "price_at_recommendation": 100, "thesis_summary": "test",
        })
        cl.record_outcome(rec_id, 100 + outcome)

    eff = cl.get_component_effectiveness(min_samples=20)
    adaptive = compute_adaptive_weights(eff)

    assert adaptive["adaptive"] is True
    assert adaptive["weights"]["company"] > WEIGHTS["company"], \
        "strongly-correlated component should gain weight"
    assert abs(sum(adaptive["weights"].values()) - 1.0) < 1e-6, \
        "adjusted weights must still sum to 1.0"


def test_negative_correlation_shifts_weight_down(tmp_path):
    _isolated_cl(tmp_path)
    random.seed(7)
    for i in range(30):
        technical = random.uniform(20, 90)
        outcome = (50 - technical) * 0.6 + random.uniform(-3, 3)  # inverse signal
        rec_id = cl.log_recommendation(f"T{i}", {
            "company_score": random.uniform(20, 90),
            "valuation_score": random.uniform(20, 90),
            "technical_score": technical,
            "capital_flow_score": random.uniform(20, 90),
            "sector_score": random.uniform(20, 90),
            "overall_recommendation": "Buy", "confidence": "Medium",
            "price_at_recommendation": 100, "thesis_summary": "test",
        })
        cl.record_outcome(rec_id, 100 + outcome)

    eff = cl.get_component_effectiveness(min_samples=20)
    adaptive = compute_adaptive_weights(eff)

    assert adaptive["weights"]["technical"] < WEIGHTS["technical"], \
        "negatively-correlated component should lose weight"


def test_weight_adjustment_is_bounded(tmp_path):
    """Even with a perfect correlation, the adjustment must respect
    max_adjustment — a system used for real capital should never let
    one thin-history component swing to dominate everything."""
    _isolated_cl(tmp_path)
    for i in range(30):
        company = 20 + i * 2  # perfectly increasing
        outcome = company - 50  # perfectly correlated, no noise
        rec_id = cl.log_recommendation(f"T{i}", {
            "company_score": company, "valuation_score": 50,
            "technical_score": 50, "capital_flow_score": 50, "sector_score": 50,
            "overall_recommendation": "Buy", "confidence": "Medium",
            "price_at_recommendation": 100, "thesis_summary": "test",
        })
        cl.record_outcome(rec_id, 100 + outcome)

    eff = cl.get_component_effectiveness(min_samples=20)
    adaptive = compute_adaptive_weights(eff, max_adjustment=0.4)

    max_possible_raw = WEIGHTS["company"] * 1.4
    adj = adaptive["adjustments_applied"]["company"]
    assert adj["adjusted_weight"] <= max_possible_raw + 1e-6


def test_component_effectiveness_reports_sample_size_honestly(tmp_path):
    _isolated_cl(tmp_path)
    for i in range(10):
        rec_id = cl.log_recommendation(f"T{i}", {
            "company_score": 50, "valuation_score": 50, "technical_score": 50,
            "capital_flow_score": 50, "sector_score": 50,
            "overall_recommendation": "Buy", "confidence": "Medium",
            "price_at_recommendation": 100, "thesis_summary": "test",
        })
        cl.record_outcome(rec_id, 105)

    eff = cl.get_component_effectiveness(min_samples=20)
    assert eff["components"]["company_score"]["sample_size"] == 10
    assert eff["components"]["company_score"]["reliable"] is False
