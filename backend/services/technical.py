"""
technical.py — Layer 8: Technical Intelligence Engine.

Computes trend, momentum, and volatility indicators from price history
already available via DataLoader.get_price_data(). No new data source
required — pure computation on OHLCV.

Indicators:
  Trend       — SMA20, SMA50, SMA200, trend direction
  Momentum    — RSI(14), MACD(12,26,9), ADX(14)
  Volatility  — ATR(14)
  Levels      — recent support/resistance (rolling swing highs/lows)

Output: Technical Score (0-100), Entry Quality, Trend Strength, Timing
Confidence — plus the raw indicator values so the frontend can chart them.

All functions are defensive: insufficient history returns None/neutral
values rather than raising, per the "never crashes" pattern used
elsewhere in this codebase.
"""

import math
import pandas as pd
import numpy as np


def _safe_round(val, nd=2):
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, nd)
    except (TypeError, ValueError):
        return None


# ── Moving averages / trend ─────────────────────────────────────────────

def _sma(series: pd.Series, window: int):
    if len(series) < window:
        return None
    return series.rolling(window).mean().iloc[-1]


def _ema_series(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _trend_direction(close: pd.Series) -> dict:
    sma20 = _sma(close, 20)
    sma50 = _sma(close, 50)
    sma200 = _sma(close, 200)
    last = close.iloc[-1] if len(close) else None

    direction = "Neutral"
    strength = 0  # 0-10
    if last is not None and sma20 is not None and sma50 is not None:
        if sma200 is not None:
            if last > sma20 > sma50 > sma200:
                direction, strength = "Strong Uptrend", 10
            elif last > sma20 and sma20 > sma50:
                direction, strength = "Uptrend", 7
            elif last < sma20 < sma50 < sma200:
                direction, strength = "Strong Downtrend", 0
            elif last < sma20 and sma20 < sma50:
                direction, strength = "Downtrend", 3
            else:
                direction, strength = "Sideways", 5
        else:
            if last > sma20 > sma50:
                direction, strength = "Uptrend", 7
            elif last < sma20 < sma50:
                direction, strength = "Downtrend", 3
            else:
                direction, strength = "Sideways", 5

    return {
        "sma20": _safe_round(sma20),
        "sma50": _safe_round(sma50),
        "sma200": _safe_round(sma200),
        "direction": direction,
        "trend_strength": strength,  # 0-10
    }


# ── RSI(14) ──────────────────────────────────────────────────────────────

def _rsi(close: pd.Series, period: int = 14):
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    if pd.isna(val):
        return 50.0 if (avg_loss.iloc[-1] == 0 and avg_gain.iloc[-1] > 0) else None
    return float(val)


# ── MACD(12,26,9) ────────────────────────────────────────────────────────

def _macd(close: pd.Series):
    if len(close) < 35:
        return None
    ema12 = _ema_series(close, 12)
    ema26 = _ema_series(close, 26)
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal_line
    return {
        "macd": _safe_round(macd_line.iloc[-1], 4),
        "signal": _safe_round(signal_line.iloc[-1], 4),
        "histogram": _safe_round(hist.iloc[-1], 4),
        "bullish_cross": bool(
            macd_line.iloc[-1] > signal_line.iloc[-1]
            and macd_line.iloc[-2] <= signal_line.iloc[-2]
        ) if len(macd_line) > 1 else False,
        "bearish_cross": bool(
            macd_line.iloc[-1] < signal_line.iloc[-1]
            and macd_line.iloc[-2] >= signal_line.iloc[-2]
        ) if len(macd_line) > 1 else False,
    }


# ── ATR(14) and ADX(14) — both need high/low/close ──────────────────────

def _true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr


def _atr(df: pd.DataFrame, period: int = 14):
    if len(df) < period + 1:
        return None
    tr = _true_range(df)
    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    val = atr.iloc[-1]
    return None if pd.isna(val) else float(val)


def _adx(df: pd.DataFrame, period: int = 14):
    if len(df) < period * 2:
        return None
    high, low, close = df["high"], df["low"], df["close"]
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = _true_range(df)
    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(
        alpha=1 / period, min_periods=period, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(
        alpha=1 / period, min_periods=period, adjust=False).mean() / atr.replace(0, np.nan)

    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    adx = dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    val = adx.iloc[-1]
    return None if pd.isna(val) else float(val)


# ── Support / resistance (simple rolling swing levels) ──────────────────

def _support_resistance(df: pd.DataFrame, window: int = 60):
    if df.empty:
        return {"support": None, "resistance": None}
    recent = df.tail(window)
    return {
        "support": _safe_round(recent["low"].min()),
        "resistance": _safe_round(recent["high"].max()),
    }


# ── Composite score ───────────────────────────────────────────────────────

def _technical_score(trend: dict, rsi, macd: dict, adx, atr_pct) -> dict:
    """0-100 composite. Defensive against missing components — each
    contributes 0 if unavailable rather than skewing the average."""
    score = 0.0
    weight_total = 0.0

    # Trend (40 pts max)
    score += (trend["trend_strength"] / 10.0) * 40
    weight_total += 40

    # RSI (20 pts max) — reward 40-60 neutral-bullish zone, penalize extremes
    if rsi is not None:
        if 45 <= rsi <= 65:
            rsi_pts = 20
        elif 35 <= rsi < 45 or 65 < rsi <= 75:
            rsi_pts = 12
        elif rsi < 30:
            rsi_pts = 5  # oversold — risky entry but not "bad" trend
        elif rsi > 80:
            rsi_pts = 2  # overbought
        else:
            rsi_pts = 8
        score += rsi_pts
        weight_total += 20

    # MACD (25 pts max)
    if macd is not None:
        macd_pts = 0
        if macd.get("histogram") is not None:
            macd_pts = 15 if macd["histogram"] > 0 else 5
        if macd.get("bullish_cross"):
            macd_pts += 10
        score += min(macd_pts, 25)
        weight_total += 25

    # ADX (15 pts max) — trend strength regardless of direction
    if adx is not None:
        adx_pts = min(adx / 50.0, 1.0) * 15
        score += adx_pts
        weight_total += 15

    if weight_total == 0:
        return {"score": None, "confidence": "Low", "label": "Insufficient Data"}

    final = round((score / weight_total) * 100, 1)
    if final >= 70:
        label = "Strong"
    elif final >= 50:
        label = "Favorable"
    elif final >= 30:
        label = "Mixed"
    else:
        label = "Weak"

    confidence = "High" if weight_total >= 80 else ("Medium" if weight_total >= 40 else "Low")
    return {"score": final, "confidence": confidence, "label": label}


def compute_technical(price_df: pd.DataFrame) -> dict:
    """
    Main entry point. price_df must have columns: open, high, low, close, volume
    and a datetime-like index, sorted ascending. Returns a structured dict
    safe to JSON-serialize directly.
    """
    if price_df is None or price_df.empty or len(price_df) < 2:
        return {
            "available": False,
            "reason": "Insufficient price history (need 2+ data points; more for full indicators)",
            "trend": None, "rsi": None, "macd": None, "adx": None, "atr": None,
            "support_resistance": {"support": None, "resistance": None},
            "technical_score": {"score": None, "confidence": "Low", "label": "Insufficient Data"},
        }

    df = price_df.sort_index()
    close = df["close"].astype(float)

    trend = _trend_direction(close)
    rsi = _rsi(close)
    macd = _macd(close)
    adx = _adx(df) if {"high", "low"}.issubset(df.columns) else None
    atr = _atr(df) if {"high", "low"}.issubset(df.columns) else None
    atr_pct = (atr / close.iloc[-1] * 100) if (atr and close.iloc[-1]) else None
    sr = _support_resistance(df)

    tscore = _technical_score(trend, rsi, macd, adx, atr_pct)

    return {
        "available": True,
        "trend": trend,
        "rsi": _safe_round(rsi),
        "macd": macd,
        "adx": _safe_round(adx),
        "atr": _safe_round(atr),
        "atr_pct": _safe_round(atr_pct),
        "support_resistance": sr,
        "technical_score": tscore,
    }
