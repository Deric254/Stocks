"""
continuous_learning.py — Layer 12: Continuous Learning.

Stores every recommendation snapshot (ticker, scores across all layers,
market conditions, date) to a CSV, and periodically evaluates predicted
vs. actual returns once enough time has passed. This is the layer the
constitution explicitly says is only meaningful after months of
accumulated history — it starts empty and useful, not retroactively
populated.

Storage: simple append-only CSV, consistent with this codebase's
existing pattern (portfolio_trades.csv, etc.) — no new database
dependency introduced.
"""

import uuid
import pandas as pd
from datetime import datetime, timezone

from services.paths import DATA_DIR
RECOMMENDATIONS_CSV = DATA_DIR / "recommendations_log.csv"

COLUMNS = [
    "recommendation_id", "ticker", "date", "company_score", "valuation_score",
    "technical_score", "capital_flow_score", "sector_score", "risk_classification",
    "overall_recommendation", "confidence", "price_at_recommendation",
    "thesis_summary", "outcome_price", "outcome_date", "outcome_return_pct",
]


def _load() -> pd.DataFrame:
    if RECOMMENDATIONS_CSV.exists():
        try:
            df = pd.read_csv(RECOMMENDATIONS_CSV, dtype=object)
            for col in COLUMNS:
                if col not in df.columns:
                    df[col] = None
            return df[COLUMNS].astype(object)
        except Exception:
            pass
    return pd.DataFrame(columns=COLUMNS, dtype=object)


def _save(df: pd.DataFrame):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(RECOMMENDATIONS_CSV, index=False)


def log_recommendation(ticker: str, snapshot: dict) -> str:
    """
    snapshot keys (all optional except ticker): company_score,
    valuation_score, technical_score, capital_flow_score, sector_score,
    risk_classification, overall_recommendation, confidence,
    price_at_recommendation, thesis_summary
    """
    df = _load()
    rec_id = str(uuid.uuid4())
    new_row = pd.DataFrame([{
        "recommendation_id": rec_id,
        "ticker": ticker.upper(),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "company_score": snapshot.get("company_score"),
        "valuation_score": snapshot.get("valuation_score"),
        "technical_score": snapshot.get("technical_score"),
        "capital_flow_score": snapshot.get("capital_flow_score"),
        "sector_score": snapshot.get("sector_score"),
        "risk_classification": snapshot.get("risk_classification"),
        "overall_recommendation": snapshot.get("overall_recommendation"),
        "confidence": snapshot.get("confidence"),
        "price_at_recommendation": snapshot.get("price_at_recommendation"),
        "thesis_summary": snapshot.get("thesis_summary"),
        "outcome_price": None,
        "outcome_date": None,
        "outcome_return_pct": None,
    }], dtype=object)
    df = pd.concat([df, new_row], ignore_index=True).astype(object)
    _save(df)
    return rec_id


def record_outcome(recommendation_id: str, current_price: float) -> dict:
    """Backfill the outcome for a past recommendation given a current price."""
    df = _load()
    mask = df["recommendation_id"] == recommendation_id
    if not mask.any():
        return {"success": False, "reason": "recommendation_id not found"}

    row = df[mask].iloc[0]
    entry_price = row.get("price_at_recommendation")
    return_pct = None
    if entry_price and float(entry_price) > 0:
        return_pct = round((current_price - float(entry_price)) / float(entry_price) * 100, 2)

    df.loc[mask, "outcome_price"] = current_price
    df.loc[mask, "outcome_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    df.loc[mask, "outcome_return_pct"] = return_pct
    _save(df)
    return {"success": True, "return_pct": return_pct}


def get_recommendation_history(ticker: str = None) -> list:
    df = _load()
    if ticker:
        df = df[df["ticker"] == ticker.upper()]
    df = df.where(pd.notna(df), None)
    return df.to_dict(orient="records")


def get_component_effectiveness(min_samples: int = 20) -> dict:
    """
    The actual 'continuous learning' mechanism: correlates each Layer 10
    component's historical score against the REAL outcome_return_pct of
    recommendations that have since been evaluated. This is what lets
    recommendation.py adjust its weights based on what has actually
    worked, rather than the static defaults forever.

    Gated by min_samples: with too few evaluated recommendations, a
    correlation is statistical noise, not a signal. Below the threshold,
    every component reports not-yet-reliable rather than a misleading
    number — this is deliberate, not a missing feature. Overfitting
    weights to 5 data points would make the system WORSE, not better,
    which matters more than usual given this feeds a system used for
    real capital decisions.
    """
    df = _load()
    evaluated = df[df["outcome_return_pct"].notna()].copy()
    evaluated["outcome_return_pct"] = pd.to_numeric(evaluated["outcome_return_pct"], errors="coerce")

    components = ["company_score", "valuation_score", "technical_score", "capital_flow_score", "sector_score"]
    results = {}

    for comp in components:
        evaluated[comp] = pd.to_numeric(evaluated[comp], errors="coerce")
        paired = evaluated[[comp, "outcome_return_pct"]].dropna()
        n = len(paired)

        if n < min_samples:
            results[comp] = {
                "reliable": False,
                "sample_size": n,
                "min_samples_required": min_samples,
                "correlation": None,
                "reason": f"Only {n} evaluated recommendations with this component present — "
                          f"need {min_samples}+ before trusting a correlation.",
            }
            continue

        corr = paired[comp].corr(paired["outcome_return_pct"])
        results[comp] = {
            "reliable": True,
            "sample_size": n,
            "correlation": round(float(corr), 3) if corr is not None and not pd.isna(corr) else None,
            "interpretation": (
                "Strong predictive signal" if corr is not None and abs(corr) > 0.5 else
                "Moderate predictive signal" if corr is not None and abs(corr) > 0.25 else
                "Weak predictive signal" if corr is not None else "Undefined (no variance in data)"
            ),
        }

    return {
        "total_evaluated": len(evaluated),
        "min_samples_required": min_samples,
        "components": results,
    }


def get_accuracy_stats() -> dict:
    """
    Aggregate stats on how well past recommendations performed —
    only meaningful once outcomes have been backfilled over time.
    Per constitution: this layer 'continuously evaluates which
    indicators improve investment performance' — this is the
    foundational aggregation that future indicator-weighting work
    would build on.
    """
    df = _load()
    evaluated = df[df["outcome_return_pct"].notna()]

    if evaluated.empty:
        return {
            "available": False,
            "reason": "No recommendations have recorded outcomes yet. This is expected for a "
                      "new system — accuracy stats accumulate meaning over months, not immediately.",
            "total_recommendations_logged": len(df),
        }

    evaluated = evaluated.copy()
    evaluated["outcome_return_pct"] = pd.to_numeric(evaluated["outcome_return_pct"], errors="coerce")

    buy_recs = evaluated[evaluated["overall_recommendation"].astype(str).str.contains("Buy", case=False, na=False)]
    hit_rate = None
    if not buy_recs.empty:
        hit_rate = round((buy_recs["outcome_return_pct"] > 0).mean() * 100, 1)

    return {
        "available": True,
        "total_recommendations_logged": len(df),
        "total_with_outcomes": len(evaluated),
        "avg_return_pct": round(evaluated["outcome_return_pct"].mean(), 2),
        "median_return_pct": round(evaluated["outcome_return_pct"].median(), 2),
        "buy_recommendation_hit_rate_pct": hit_rate,
        "best_call": evaluated.loc[evaluated["outcome_return_pct"].idxmax()][["ticker", "date", "outcome_return_pct"]].to_dict() if not evaluated.empty else None,
        "worst_call": evaluated.loc[evaluated["outcome_return_pct"].idxmin()][["ticker", "date", "outcome_return_pct"]].to_dict() if not evaluated.empty else None,
    }
