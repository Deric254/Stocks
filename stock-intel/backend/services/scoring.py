"""
scoring.py — Ndindi-style scoring engine.

Produces four scores (0–100) per stock:
  D  = Daily Score     (most undervalued today)
  M  = Monthly Score   (fundamentally strong)
  L  = Long-Term Score (best long-term value)
  BP = Best Pick       (0.4*D + 0.3*M + 0.3*L)

All sub-scores use min-max normalisation so the engine is
self-calibrating even when absolute values differ by market.
"""

import math
import numpy as np
import pandas as pd


# ──────────────────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _norm(value: float, min_val: float, max_val: float, invert: bool = False) -> float:
    """Min-max normalise to [0, 100].  If invert=True, lower is better."""
    if max_val == min_val:
        return 50.0
    score = (value - min_val) / (max_val - min_val) * 100
    score = max(0.0, min(100.0, score))
    return 100.0 - score if invert else score


def _safe(value, default=0.0) -> float:
    """Return float or default if None / NaN."""
    if value is None:
        return default
    try:
        f = float(value)
        return default if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return default


def _pct_change(series: pd.Series, periods: int = 1) -> float:
    """Percentage change over `periods` rows, clamped to [-1, 1]."""
    if len(series) <= periods:
        return 0.0
    old = _safe(series.iloc[-(periods + 1)])
    new = _safe(series.iloc[-1])
    if old == 0:
        return 0.0
    return max(-1.0, min(1.0, (new - old) / old))


# ──────────────────────────────────────────────────────────────────────────────
#  Score components
# ──────────────────────────────────────────────────────────────────────────────

def _daily_score(prices: pd.DataFrame, fund: dict) -> float:
    """
    Daily Score — "Most undervalued today"
    Factors (equally weighted):
      1. P/B ratio         (lower = better)
      2. P/E ratio         (lower = better)
      3. Price vs 52-wk low (closer to low = more undervalued)
      4. Dividend yield    (higher = better)
      5. Daily volatility  (lower = better — less risky on entry)
    """
    scores = []

    # 1. P/B (invert — lower P/B → more undervalued)
    pb = _safe(fund.get("pb"), 2.0)
    scores.append(_norm(pb, 0.5, 5.0, invert=True))

    # 2. P/E (invert)
    pe = _safe(fund.get("pe"), 15.0)
    scores.append(_norm(pe, 3.0, 40.0, invert=True))

    # 3. Price vs 52-week low
    if not prices.empty and len(prices) >= 2:
        close = prices["close"]
        low_52  = float(close.tail(252).min())
        high_52 = float(close.tail(252).max())
        current = float(close.iloc[-1])
        # Score 100 when price == 52-week low, 0 when at high
        scores.append(_norm(current, low_52, high_52, invert=True))
    else:
        scores.append(50.0)

    # 4. Dividend yield (higher is better)
    dy = _safe(fund.get("dividend_yield"), 0.0)
    scores.append(_norm(dy, 0.0, 0.15, invert=False))

    # 5. Daily volatility (invert — lower vol = safer entry)
    if not prices.empty and len(prices) >= 20:
        daily_returns = prices["close"].pct_change().dropna().tail(20)
        vol = float(daily_returns.std()) if len(daily_returns) > 1 else 0.05
    else:
        vol = 0.05
    scores.append(_norm(vol, 0.0, 0.05, invert=True))

    return round(float(np.mean(scores)), 1)


def _monthly_score(prices: pd.DataFrame, fund: dict) -> float:
    """
    Monthly Score — "Most fundamentally strong"
    Factors:
      1. 1-month price trend   (positive = good)
      2. Volume trend          (rising volume = good)
      3. EPS                   (higher = better)
      4. Revenue trend proxy   (using EPS as proxy if no history)
      5. Debt/Equity           (lower = better)
      6. Dividend yield        (higher = better)
    """
    scores = []

    # 1. 1-month price trend (20 trading days)
    if not prices.empty and len(prices) >= 20:
        trend_1m = _pct_change(prices["close"], 20)
    else:
        trend_1m = 0.0
    scores.append(_norm(trend_1m, -0.15, 0.15))

    # 2. Volume trend
    if not prices.empty and len(prices) >= 20:
        vol_trend = _pct_change(prices["volume"], 20)
    else:
        vol_trend = 0.0
    scores.append(_norm(vol_trend, -0.5, 0.5))

    # 3. EPS (higher = better)
    eps = _safe(fund.get("eps"), 0.0)
    scores.append(_norm(eps, -5.0, 20.0))

    # 4. Revenue (higher = better; normalised in billions)
    revenue = _safe(fund.get("revenue"), 0.0) / 1e9
    scores.append(_norm(revenue, 0.0, 500.0))

    # 5. Debt / Equity proxy (lower debt relative to book value = better)
    debt = _safe(fund.get("debt"), 0.0)
    bvps = _safe(fund.get("bvps"), 1.0)
    # Rough D/E via total debt / (bvps * some share count proxy)
    # We normalise the debt figure directly since we lack share count
    scores.append(_norm(debt / 1e9, 0.0, 200.0, invert=True))

    # 6. Dividend yield
    dy = _safe(fund.get("dividend_yield"), 0.0)
    scores.append(_norm(dy, 0.0, 0.15))

    return round(float(np.mean(scores)), 1)


def _longterm_score(prices: pd.DataFrame, fund: dict) -> float:
    """
    Long-Term Score — "Best long-term value picks"
    Factors:
      1. 1-year price trend
      2. EPS quality (positive EPS = good)
      3. Dividend yield + consistency proxy
      4. ROE                   (higher = better)
      5. Profit margin         (higher = better)
      6. P/B ratio             (lower = better for value investors)
    """
    scores = []

    # 1. 1-year price trend (252 trading days)
    if not prices.empty and len(prices) >= 252:
        trend_1y = _pct_change(prices["close"], 252)
    elif not prices.empty:
        trend_1y = _pct_change(prices["close"], len(prices) - 1)
    else:
        trend_1y = 0.0
    scores.append(_norm(trend_1y, -0.3, 0.5))

    # 2. EPS quality
    eps = _safe(fund.get("eps"), 0.0)
    scores.append(_norm(eps, -5.0, 20.0))

    # 3. Dividend (consistency proxy = yield > 0 is consistent; higher = better)
    dy = _safe(fund.get("dividend_yield"), 0.0)
    scores.append(_norm(dy, 0.0, 0.15))

    # 4. ROE (higher = better; normalise 0–40%)
    roe = _safe(fund.get("roe"), 0.0)
    scores.append(_norm(roe, 0.0, 0.40))

    # 5. Profit margin (higher = better; normalise 0–50%)
    margin = _safe(fund.get("margin"), 0.0)
    scores.append(_norm(margin, 0.0, 0.50))

    # 6. P/B (lower = better — value pick)
    pb = _safe(fund.get("pb"), 2.0)
    scores.append(_norm(pb, 0.5, 5.0, invert=True))

    return round(float(np.mean(scores)), 1)


# ──────────────────────────────────────────────────────────────────────────────
#  Public interface
# ──────────────────────────────────────────────────────────────────────────────

class ScoringEngine:

    def compute_scores(self, prices: pd.DataFrame, fund: dict) -> dict:
        """
        Compute D, M, L, BP scores for a single stock.

        Parameters
        ----------
        prices : pd.DataFrame
            OHLCV dataframe with DatetimeIndex (from DataLoader).
        fund : dict
            Fundamentals dict (from DataLoader).

        Returns
        -------
        dict with keys: daily, monthly, long_term, best_pick
        """
        d = _daily_score(prices, fund)
        m = _monthly_score(prices, fund)
        l = _longterm_score(prices, fund)
        bp = round(0.4 * d + 0.3 * m + 0.3 * l, 1)

        return {
            "daily":      d,
            "monthly":    m,
            "long_term":  l,
            "best_pick":  bp,
        }
