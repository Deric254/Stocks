"""
capital_flow.py — Layer 7: Capital Flow Engine.

True institutional buying/selling, ETF flows, and large-transaction
data are not available for free for the NSE (or most markets). This
module is honest about that ceiling: it computes what's actually
derivable for free from data already in this codebase — volume-based
accumulation/distribution and breadth — and explicitly labels
everything else as unavailable rather than approximating it with
something misleading.

Computed (real, free, from your own price+volume history):
  - On-Balance Volume (OBV) trend
  - Accumulation/Distribution Line (Chaikin)
  - Volume-weighted momentum (is volume confirming the price move?)
  - Relative volume (today/recent vs. its own historical average)

NOT available without paid data (explicitly flagged, never faked):
  - Institutional buying/selling
  - Foreign investor flows
  - ETF/fund flows
  - Large block transactions
  - Market-wide breadth (needs full-market data feed)
"""

import math
import pandas as pd
import numpy as np


def _safe_round(val, nd=2):
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, nd)
    except (TypeError, ValueError):
        return None


def _obv(df: pd.DataFrame) -> pd.Series:
    close = df["close"].astype(float)
    volume = df["volume"].astype(float)
    direction = np.sign(close.diff().fillna(0))
    return (direction * volume).cumsum()


def _accumulation_distribution(df: pd.DataFrame) -> pd.Series:
    high, low, close, vol = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float), df["volume"].astype(float)
    range_ = (high - low).replace(0, np.nan)
    mfm = ((close - low) - (high - close)) / range_  # money flow multiplier
    mfm = mfm.fillna(0)
    mfv = mfm * vol  # money flow volume
    return mfv.cumsum()


def compute_capital_flow(price_df: pd.DataFrame) -> dict:
    """Main entry point — Layer 7 output for a single ticker."""
    if price_df is None or price_df.empty or len(price_df) < 10:
        return {
            "available": False,
            "reason": "Need 10+ price/volume data points for capital flow analysis",
            "unavailable_metrics": [
                "institutional_buying", "institutional_selling",
                "foreign_investor_flows", "etf_fund_flows", "large_transactions",
            ],
            "unavailable_note": (
                "These require paid institutional data feeds not available for "
                "the NSE for free. Marked unavailable rather than approximated."
            ),
        }

    df = price_df.sort_index().copy()
    has_volume = "volume" in df.columns and df["volume"].sum() > 0

    if not has_volume:
        return {
            "available": False,
            "reason": "Price history has no volume data — upload volume alongside OHLC to enable this layer",
            "unavailable_metrics": [
                "institutional_buying", "institutional_selling",
                "foreign_investor_flows", "etf_fund_flows", "large_transactions",
            ],
        }

    obv = _obv(df)
    ad_line = _accumulation_distribution(df)

    obv_recent = obv.tail(20)
    obv_trend = "Accumulation" if obv_recent.iloc[-1] > obv_recent.iloc[0] else "Distribution"
    obv_slope_pct = None
    if obv_recent.iloc[0] != 0:
        obv_slope_pct = _safe_round((obv_recent.iloc[-1] - obv_recent.iloc[0]) / abs(obv_recent.iloc[0]) * 100, 1)

    ad_recent = ad_line.tail(20)
    ad_trend = "Accumulation" if ad_recent.iloc[-1] > ad_recent.iloc[0] else "Distribution"

    # Relative volume — last value vs trailing 20-period average
    avg_vol = df["volume"].tail(20).mean()
    last_vol = df["volume"].iloc[-1]
    rel_volume = _safe_round(last_vol / avg_vol, 2) if avg_vol else None

    # Volume-confirmed move: did price move on above-average volume?
    price_chg_pct = _safe_round((df["close"].iloc[-1] - df["close"].iloc[-2]) / df["close"].iloc[-2] * 100, 2) if len(df) >= 2 and df["close"].iloc[-2] else None
    volume_confirmed = bool(rel_volume and rel_volume > 1.2 and price_chg_pct is not None)

    # Composite capital-flow score (0-100) — agreement between OBV and A/D trend
    agree = (obv_trend == ad_trend)
    base_score = 65 if obv_trend == "Accumulation" else 35
    if agree:
        score = base_score + (10 if obv_trend == "Accumulation" else -10)
    else:
        score = 50  # mixed signal
    score = max(0, min(100, score))

    return {
        "available": True,
        "obv_trend": obv_trend,
        "obv_slope_pct_20d": obv_slope_pct,
        "ad_line_trend": ad_trend,
        "signals_agree": agree,
        "relative_volume": rel_volume,
        "relative_volume_note": "1.0 = average; >1.2 = elevated activity",
        "volume_confirmed_last_move": volume_confirmed,
        "capital_flow_score": score,
        "capital_flow_label": (
            "Strong Accumulation" if score >= 70 else
            "Mild Accumulation" if score >= 55 else
            "Neutral / Mixed" if score >= 45 else
            "Mild Distribution" if score >= 30 else
            "Strong Distribution"
        ),
        "unavailable_metrics": [
            "institutional_buying", "institutional_selling",
            "foreign_investor_flows", "etf_fund_flows", "large_transactions",
        ],
        "unavailable_note": (
            "These require paid institutional data feeds (e.g. Bloomberg, "
            "Refinitiv) not available for the NSE for free. The metrics above "
            "are real, computed from your own volume data — not a substitute "
            "for true smart-money flow, but a legitimate free proxy."
        ),
    }
