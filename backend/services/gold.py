"""
gold.py — Gold (XAUUSD) trading module.

Live prices: Twelve Data free API (reliable, 800 req/day free)
Fallback:    Alpha Vantage free API

Strategy: Multi-timeframe trend-following
  - EMA 9/21/50/200 trend structure
  - MACD histogram momentum
  - RSI timing filter (40-60 zone for entries)
  - ATR-based dynamic SL/TP (min 3:1 RR)
  - S&R levels auto-detected from price history
  - Fibonacci retracement levels
  - Signal quality score (0-100)

Backtest: replays strategy on historical OHLCV data
Forward test: tracks paper trades from signal fire date
"""

import math
import json
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

DATA_DIR      = Path(__file__).parent.parent / "data"
GOLD_DIR      = DATA_DIR / "gold"
GOLD_DIR.mkdir(parents=True, exist_ok=True)

SIGNALS_FILE  = GOLD_DIR / "signals.json"
TRADES_FILE   = GOLD_DIR / "demo_trades.json"
BT_CACHE      = GOLD_DIR / "backtest_cache.json"
PRICES_FILE   = GOLD_DIR / "prices_cache.json"

# Free API keys — Twelve Data (primary), Alpha Vantage (fallback)
TWELVE_KEY    = "9d934205b1b1423ba8c75961658cec97"          # replace with real key from twelvedata.com (free)
AV_KEY        = "demo"          # replace with real key from alphavantage.co (free)


# ── Helpers ────────────────────────────────────────────────────────────────

def _safe(v, d=0.0):
    if v is None: return d
    try:
        f = float(v)
        return d if (math.isnan(f) or math.isinf(f)) else f
    except: return d

def _load_json(path, default):
    if path.exists():
        try:
            with open(path) as f: return json.load(f)
        except: pass
    return default

def _save_json(path, data):
    with open(path, "w") as f: json.dump(data, f, indent=2, default=str)


# ── Live Price Fetcher ──────────────────────────────────────────────────────

def fetch_live_price() -> dict:
    """Fetch current XAUUSD price. Tries multiple free sources."""

    # Source 1: Twelve Data
    try:
        url = f"https://api.twelvedata.com/price?symbol=XAU/USD&apikey={TWELVE_KEY}"
        r = requests.get(url, timeout=8)
        d = r.json()
        if "price" in d:
            price = float(d["price"])
            return {"price": price, "source": "TwelveData", "time": datetime.now().isoformat()}
    except: pass

    # Source 2: Alpha Vantage
    try:
        url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency=XAU&to_currency=USD&apikey={AV_KEY}"
        r = requests.get(url, timeout=8)
        d = r.json()
        rate = d.get("Realtime Currency Exchange Rate", {}).get("5. Exchange Rate")
        if rate:
            return {"price": float(rate), "source": "AlphaVantage", "time": datetime.now().isoformat()}
    except: pass

    # Source 3: Open exchange rates (gold proxy via metals-api pattern)
    try:
        url = "https://api.metals.live/v1/spot/gold"
        r = requests.get(url, timeout=8)
        d = r.json()
        if isinstance(d, list) and d:
            price = float(d[0].get("price", 0))
            if price > 0:
                return {"price": price, "source": "MetalsLive", "time": datetime.now().isoformat()}
    except: pass

    # Source 4: Last cached price as fallback
    cached = _load_json(PRICES_FILE, {})
    if cached.get("candles"):
        last = cached["candles"][-1]
        return {"price": float(last["close"]), "source": "cached", "time": last.get("datetime", "")}

    return {"price": 0, "source": "unavailable", "time": datetime.now().isoformat()}


def fetch_ohlcv(interval: str = "1h", outputsize: int = 500) -> pd.DataFrame:
    """
    Fetch XAUUSD OHLCV candles.
    interval: "15min" | "30min" | "1h" | "4h" | "1day"
    """
    cache = _load_json(PRICES_FILE, {})
    cache_key = f"{interval}_{outputsize}"
    cached_entry = cache.get(cache_key)

    # Use cache if less than 15 mins old
    if cached_entry:
        age = (datetime.now() - datetime.fromisoformat(cached_entry["fetched_at"])).total_seconds()
        if age < 900:
            try:
                df = pd.DataFrame(cached_entry["candles"])
                df["datetime"] = pd.to_datetime(df["datetime"])
                df = df.set_index("datetime").sort_index()
                for col in ["open","high","low","close","volume"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                return df
            except: pass

    # Twelve Data
    try:
        url = (f"https://api.twelvedata.com/time_series"
               f"?symbol=XAU/USD&interval={interval}&outputsize={outputsize}&apikey={TWELVE_KEY}")
        r = requests.get(url, timeout=15)
        d = r.json()
        if "values" in d and d["values"]:
            rows = []
            for v in reversed(d["values"]):
                rows.append({
                    "datetime": v["datetime"],
                    "open":   float(v["open"]),
                    "high":   float(v["high"]),
                    "low":    float(v["low"]),
                    "close":  float(v["close"]),
                    "volume": float(v.get("volume", 0)),
                })
            df = pd.DataFrame(rows)
            df["datetime"] = pd.to_datetime(df["datetime"])
            df = df.set_index("datetime").sort_index()

            # Save to cache
            cache[cache_key] = {
                "fetched_at": datetime.now().isoformat(),
                "candles": rows
            }
            _save_json(PRICES_FILE, cache)
            return df
    except Exception as e:
        print(f"[Gold] Twelve Data fetch failed: {e}")

    # Alpha Vantage fallback
    try:
        av_interval_map = {"15min":"15min","30min":"30min","1h":"60min","4h":"60min","1day":"Daily"}
        av_func = "FX_INTRADAY" if interval != "1day" else "FX_DAILY"
        av_int  = av_interval_map.get(interval, "60min")
        if av_func == "FX_INTRADAY":
            url = (f"https://www.alphavantage.co/query?function={av_func}"
                   f"&from_symbol=XAU&to_symbol=USD&interval={av_int}"
                   f"&outputsize=full&apikey={AV_KEY}")
        else:
            url = (f"https://www.alphavantage.co/query?function={av_func}"
                   f"&from_symbol=XAU&to_symbol=USD&outputsize=full&apikey={AV_KEY}")
        r  = requests.get(url, timeout=15)
        d  = r.json()
        key = [k for k in d.keys() if "Time Series" in k]
        if key:
            series = d[key[0]]
            rows = []
            for dt_str, vals in sorted(series.items()):
                rows.append({
                    "datetime": dt_str,
                    "open":  float(vals.get("1. open", 0)),
                    "high":  float(vals.get("2. high", 0)),
                    "low":   float(vals.get("3. low",  0)),
                    "close": float(vals.get("4. close",0)),
                    "volume": 0.0,
                })
            df = pd.DataFrame(rows)
            df["datetime"] = pd.to_datetime(df["datetime"])
            df = df.set_index("datetime").sort_index()
            cache[cache_key] = {"fetched_at": datetime.now().isoformat(), "candles": rows}
            _save_json(PRICES_FILE, cache)
            return df
    except Exception as e:
        print(f"[Gold] Alpha Vantage fallback failed: {e}")

    return pd.DataFrame()


# ── Technical Indicators ───────────────────────────────────────────────────

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hi, lo, cl = df["high"], df["low"], df["close"]
    prev_cl = cl.shift(1)
    tr = pd.concat([hi - lo, (hi - prev_cl).abs(), (lo - prev_cl).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()

def macd(series: pd.Series, fast=12, slow=26, signal=9):
    e_fast   = ema(series, fast)
    e_slow   = ema(series, slow)
    line     = e_fast - e_slow
    sig_line = ema(line, signal)
    hist     = line - sig_line
    return line, sig_line, hist

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).ewm(span=period, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(span=period, adjust=False).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def support_resistance(df: pd.DataFrame, lookback: int = 50, n_levels: int = 5) -> dict:
    """Auto-detect S&R levels from recent swing highs/lows."""
    recent = df.tail(lookback)
    highs  = recent["high"].nlargest(n_levels).values.tolist()
    lows   = recent["low"].nsmallest(n_levels).values.tolist()
    return {"resistance": sorted(highs, reverse=True), "support": sorted(lows, reverse=True)}

def fibonacci_levels(df: pd.DataFrame, lookback: int = 100) -> dict:
    """Fibonacci retracement levels from recent swing high/low."""
    recent   = df.tail(lookback)
    swing_hi = float(recent["high"].max())
    swing_lo = float(recent["low"].min())
    diff     = swing_hi - swing_lo
    ratios   = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
    levels   = {}
    for r in ratios:
        levels[f"{int(r*100)}%"] = round(swing_hi - diff * r, 2)
    levels["swing_high"] = round(swing_hi, 2)
    levels["swing_low"]  = round(swing_lo, 2)
    return levels


# ── Strategy Engine ────────────────────────────────────────────────────────

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all indicator columns to OHLCV dataframe."""
    df = df.copy()
    df["ema9"]  = ema(df["close"], 9)
    df["ema21"] = ema(df["close"], 21)
    df["ema50"] = ema(df["close"], 50)
    df["ema200"]= ema(df["close"], 200)
    df["atr14"] = atr(df, 14)
    df["rsi14"] = rsi(df["close"], 14)
    ml, ms, mh  = macd(df["close"])
    df["macd_line"] = ml
    df["macd_sig"]  = ms
    df["macd_hist"] = mh
    return df


def score_signal(row, prev_row, sr_levels: dict, fib_levels: dict, trend: str) -> dict:
    """
    Score a potential entry. Returns score 0-100 and breakdown.
    trend: "bull" | "bear"
    """
    score    = 0
    reasons  = []
    warnings = []

    price = _safe(row["close"])
    atr_v = _safe(row["atr14"])

    # 1. Trend alignment (EMA structure) — 25 pts
    ema9  = _safe(row["ema9"])
    ema21 = _safe(row["ema21"])
    ema50 = _safe(row["ema50"])
    ema200= _safe(row["ema200"])

    if trend == "bull":
        if price > ema200:
            score += 10; reasons.append("Price above EMA200 ✅")
        else:
            warnings.append("Price below EMA200 ⚠️")
        if ema50 > ema200:
            score += 8; reasons.append("EMA50 > EMA200 (golden zone) ✅")
        if ema9 > ema21:
            score += 7; reasons.append("EMA9 > EMA21 (short-term bullish) ✅")
    else:
        if price < ema200:
            score += 10; reasons.append("Price below EMA200 ✅")
        else:
            warnings.append("Price above EMA200 ⚠️")
        if ema50 < ema200:
            score += 8; reasons.append("EMA50 < EMA200 (death zone) ✅")
        if ema9 < ema21:
            score += 7; reasons.append("EMA9 < EMA21 (short-term bearish) ✅")

    # 2. MACD momentum — 20 pts
    hist      = _safe(row["macd_hist"])
    prev_hist = _safe(prev_row["macd_hist"])
    if trend == "bull" and hist > 0 and hist > prev_hist:
        score += 20; reasons.append("MACD histogram rising above zero ✅")
    elif trend == "bull" and hist > prev_hist:
        score += 10; reasons.append("MACD histogram turning up ✅")
    elif trend == "bear" and hist < 0 and hist < prev_hist:
        score += 20; reasons.append("MACD histogram falling below zero ✅")
    elif trend == "bear" and hist < prev_hist:
        score += 10; reasons.append("MACD histogram turning down ✅")
    else:
        warnings.append("MACD not confirming direction ⚠️")

    # 3. RSI timing — 20 pts
    rsi_v = _safe(row["rsi14"])
    if trend == "bull":
        if 40 <= rsi_v <= 60:
            score += 20; reasons.append(f"RSI {rsi_v:.1f} — ideal entry zone (40-60) ✅")
        elif rsi_v < 40:
            score += 12; reasons.append(f"RSI {rsi_v:.1f} — oversold, possible bounce ✅")
        elif rsi_v > 70:
            warnings.append(f"RSI {rsi_v:.1f} — overbought, risky entry ⚠️")
    else:
        if 40 <= rsi_v <= 60:
            score += 20; reasons.append(f"RSI {rsi_v:.1f} — ideal entry zone (40-60) ✅")
        elif rsi_v > 60:
            score += 12; reasons.append(f"RSI {rsi_v:.1f} — overbought, possible drop ✅")
        elif rsi_v < 30:
            warnings.append(f"RSI {rsi_v:.1f} — oversold, risky short ⚠️")

    # 4. S&R proximity — 20 pts
    if trend == "bull" and sr_levels.get("support"):
        nearest_sup = min(sr_levels["support"], key=lambda x: abs(x - price))
        dist_pct    = abs(price - nearest_sup) / price * 100
        if dist_pct < 0.5:
            score += 20; reasons.append(f"At support level ${nearest_sup:.2f} ✅")
        elif dist_pct < 1.0:
            score += 12; reasons.append(f"Near support ${nearest_sup:.2f} ({dist_pct:.1f}% away) ✅")
    elif trend == "bear" and sr_levels.get("resistance"):
        nearest_res = min(sr_levels["resistance"], key=lambda x: abs(x - price))
        dist_pct    = abs(price - nearest_res) / price * 100
        if dist_pct < 0.5:
            score += 20; reasons.append(f"At resistance level ${nearest_res:.2f} ✅")
        elif dist_pct < 1.0:
            score += 12; reasons.append(f"Near resistance ${nearest_res:.2f} ({dist_pct:.1f}% away) ✅")

    # 5. Fibonacci confluence — 15 pts
    fib_vals = [v for k, v in fib_levels.items() if k not in ("swing_high","swing_low")]
    if fib_vals:
        nearest_fib = min(fib_vals, key=lambda x: abs(x - price))
        dist_pct    = abs(price - nearest_fib) / price * 100
        if dist_pct < 0.3:
            score += 15; reasons.append(f"At Fibonacci level ${nearest_fib:.2f} ✅")
        elif dist_pct < 0.8:
            score += 8;  reasons.append(f"Near Fibonacci ${nearest_fib:.2f} ✅")

    # Quality label
    if score >= 75:
        quality = "A-Grade"
        quality_color = "#49A078"
    elif score >= 55:
        quality = "High"
        quality_color = "#86efac"
    elif score >= 35:
        quality = "Medium"
        quality_color = "#facc15"
    else:
        quality = "Low"
        quality_color = "#f97316"

    return {
        "score": min(score, 100),
        "quality": quality,
        "quality_color": quality_color,
        "reasons": reasons,
        "warnings": warnings,
    }


def generate_signal(df_h4: pd.DataFrame, df_h1: pd.DataFrame, df_m30: pd.DataFrame) -> dict:
    """
    Generate current trading signal using multi-timeframe analysis.
    H4 = trend direction
    H1 = entry timing
    M30 = precise entry
    """
    if df_h4.empty or len(df_h4) < 200:
        return {"signal": "NO_DATA", "reason": "Insufficient price history"}

    df_h4 = compute_indicators(df_h4)
    df_h1 = compute_indicators(df_h1) if not df_h1.empty else df_h4
    df_m30= compute_indicators(df_m30) if not df_m30.empty else df_h1

    # Current candle
    row_h4   = df_h4.iloc[-1]
    prev_h4  = df_h4.iloc[-2]
    row_h1   = df_h1.iloc[-1]
    row_m30  = df_m30.iloc[-1]
    prev_m30 = df_m30.iloc[-2]

    price    = _safe(row_m30["close"])
    atr_v    = _safe(row_m30["atr14"])

    # Determine trend from H4
    ema50_h4  = _safe(row_h4["ema50"])
    ema200_h4 = _safe(row_h4["ema200"])
    close_h4  = _safe(row_h4["close"])

    if close_h4 > ema50_h4 and ema50_h4 > ema200_h4:
        trend = "bull"
        direction = "BUY"
    elif close_h4 < ema50_h4 and ema50_h4 < ema200_h4:
        trend = "bear"
        direction = "SELL"
    else:
        trend = "neutral"
        direction = "WAIT"

    if trend == "neutral":
        return {
            "signal":    "WAIT",
            "direction": "WAIT",
            "price":     round(price, 2),
            "reason":    "Market structure unclear — EMA50 and EMA200 are intertwined. Wait for clear trend.",
            "score":     0,
            "quality":   "Low",
            "quality_color": "#9ca3af",
            "reasons":   [],
            "warnings":  ["No clear trend on H4 — standing aside"],
            "entry":     None, "sl": None, "tp1": None, "tp2": None, "rr": None,
            "atr":       round(atr_v, 2),
            "generated_at": datetime.now().isoformat(),
        }

    # S&R and Fibonacci from H4
    sr  = support_resistance(df_h4, lookback=100)
    fib = fibonacci_levels(df_h4, lookback=200)

    # Score using M30 for entry precision
    scored = score_signal(row_m30, prev_m30, sr, fib, trend)

    # Entry, SL, TP
    entry = round(price, 2)
    sl_dist  = round(atr_v * 1.5, 2)
    tp1_dist = round(atr_v * 4.5, 2)   # 3:1
    tp2_dist = round(atr_v * 7.5, 2)   # 5:1

    if direction == "BUY":
        sl  = round(entry - sl_dist, 2)
        tp1 = round(entry + tp1_dist, 2)
        tp2 = round(entry + tp2_dist, 2)
    else:
        sl  = round(entry + sl_dist, 2)
        tp1 = round(entry - tp1_dist, 2)
        tp2 = round(entry - tp2_dist, 2)

    rr = round(tp1_dist / sl_dist, 2) if sl_dist > 0 else 0

    return {
        "signal":      "ACTIVE" if scored["score"] >= 35 else "WEAK",
        "direction":   direction,
        "price":       round(price, 2),
        "entry":       entry,
        "sl":          sl,
        "tp1":         tp1,
        "tp2":         tp2,
        "rr":          rr,
        "sl_pips":     round(sl_dist, 2),
        "tp1_pips":    round(tp1_dist, 2),
        "atr":         round(atr_v, 2),
        "score":       scored["score"],
        "quality":     scored["quality"],
        "quality_color": scored["quality_color"],
        "reasons":     scored["reasons"],
        "warnings":    scored["warnings"],
        "trend":       trend,
        "sr_levels":   sr,
        "fib_levels":  fib,
        "indicators": {
            "rsi":        round(_safe(row_m30["rsi14"]), 1),
            "macd_hist":  round(_safe(row_m30["macd_hist"]), 4),
            "ema9":       round(_safe(row_m30["ema9"]), 2),
            "ema21":      round(_safe(row_m30["ema21"]), 2),
            "ema50_h4":   round(ema50_h4, 2),
            "ema200_h4":  round(ema200_h4, 2),
        },
        "generated_at": datetime.now().isoformat(),
    }


# ── Backtest Engine ────────────────────────────────────────────────────────

def run_backtest(df_raw: pd.DataFrame, start_date: str = None, end_date: str = None,
                 atr_sl_mult: float = 1.5, atr_tp_mult: float = 4.5,
                 min_score: int = 35) -> dict:
    """
    Replay strategy on historical data. Returns full trade log + stats.
    """
    if df_raw.empty or len(df_raw) < 220:
        return {"error": "Not enough data for backtest (need 220+ candles)"}

    df = compute_indicators(df_raw.copy())

    if start_date:
        df = df[df.index >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df.index <= pd.to_datetime(end_date)]

    if len(df) < 50:
        return {"error": "Date range too narrow — need at least 50 candles"}

    trades    = []
    in_trade  = False
    trade     = {}
    equity    = [{"date": str(df.index[0].date()), "value": 10000.0}]
    balance   = 10000.0
    risk_pct  = 0.01   # 1% risk per trade

    for i in range(200, len(df)):
        row      = df.iloc[i]
        prev_row = df.iloc[i - 1]
        price    = _safe(row["close"])
        atr_v    = _safe(row["atr14"])
        date_str = str(df.index[i])

        if in_trade:
            # Check SL/TP hit
            hi = _safe(row["high"])
            lo = _safe(row["low"])

            hit_sl  = (trade["direction"] == "BUY"  and lo <= trade["sl"])  or \
                      (trade["direction"] == "SELL" and hi >= trade["sl"])
            hit_tp1 = (trade["direction"] == "BUY"  and hi >= trade["tp1"]) or \
                      (trade["direction"] == "SELL" and lo <= trade["tp1"])

            if hit_sl:
                pnl = -trade["risk_amount"]
                balance += pnl
                trade.update({"exit_price": trade["sl"], "exit_date": date_str,
                               "result": "SL", "pnl": round(pnl, 2), "balance": round(balance, 2)})
                trades.append(trade)
                in_trade = False
                equity.append({"date": date_str, "value": round(balance, 2)})

            elif hit_tp1:
                sl_dist  = abs(trade["entry"] - trade["sl"])
                tp1_dist = abs(trade["tp1"]   - trade["entry"])
                rr_actual = tp1_dist / sl_dist if sl_dist > 0 else 0
                pnl = trade["risk_amount"] * rr_actual
                balance += pnl
                trade.update({"exit_price": trade["tp1"], "exit_date": date_str,
                               "result": "TP1", "pnl": round(pnl, 2), "balance": round(balance, 2),
                               "rr_actual": round(rr_actual, 2)})
                trades.append(trade)
                in_trade = False
                equity.append({"date": date_str, "value": round(balance, 2)})

        else:
            # Check for new signal
            ema50_v  = _safe(row["ema50"])
            ema200_v = _safe(row["ema200"])

            if price > ema50_v and ema50_v > ema200_v:
                trend = "bull"; direction = "BUY"
            elif price < ema50_v and ema50_v < ema200_v:
                trend = "bear"; direction = "SELL"
            else:
                continue

            sr  = support_resistance(df.iloc[:i], lookback=50)
            fib = fibonacci_levels(df.iloc[:i], lookback=100)
            scored = score_signal(row, prev_row, sr, fib, trend)

            if scored["score"] < min_score:
                continue

            # Enter
            entry    = price
            sl_dist  = atr_v * atr_sl_mult
            tp1_dist = atr_v * atr_tp_mult
            risk_amt = balance * risk_pct

            if direction == "BUY":
                sl  = entry - sl_dist
                tp1 = entry + tp1_dist
            else:
                sl  = entry + sl_dist
                tp1 = entry - tp1_dist

            trade = {
                "direction":   direction,
                "entry":       round(entry, 2),
                "sl":          round(sl, 2),
                "tp1":         round(tp1, 2),
                "entry_date":  date_str,
                "score":       scored["score"],
                "quality":     scored["quality"],
                "risk_amount": round(risk_amt, 2),
                "atr":         round(atr_v, 2),
            }
            in_trade = True

    # Close any open trade at end
    if in_trade:
        last_price = _safe(df.iloc[-1]["close"])
        pnl = (last_price - trade["entry"]) * (1 if trade["direction"] == "BUY" else -1)
        pnl_scaled = trade["risk_amount"] * (pnl / abs(trade["entry"] - trade["sl"])) if trade["entry"] != trade["sl"] else 0
        balance += pnl_scaled
        trade.update({"exit_price": round(last_price, 2), "exit_date": str(df.index[-1]),
                       "result": "OPEN", "pnl": round(pnl_scaled, 2), "balance": round(balance, 2)})
        trades.append(trade)
        equity.append({"date": str(df.index[-1]), "value": round(balance, 2)})

    # Stats
    closed   = [t for t in trades if t.get("result") in ("SL","TP1")]
    wins     = [t for t in closed if t["result"] == "TP1"]
    losses   = [t for t in closed if t["result"] == "SL"]
    win_rate = len(wins) / len(closed) * 100 if closed else 0
    total_pnl= sum(t["pnl"] for t in closed)
    avg_win  = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    profit_factor = abs(sum(t["pnl"] for t in wins) / sum(t["pnl"] for t in losses)) if losses and sum(t["pnl"] for t in losses) != 0 else 999

    # Max drawdown
    peak = 10000.0
    max_dd = 0.0
    for e in equity:
        v = e["value"]
        if v > peak: peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd: max_dd = dd

    return {
        "trades":         trades,
        "equity_curve":   equity,
        "stats": {
            "total_trades":   len(closed),
            "wins":           len(wins),
            "losses":         len(losses),
            "win_rate":       round(win_rate, 1),
            "total_pnl":      round(total_pnl, 2),
            "avg_win":        round(avg_win, 2),
            "avg_loss":       round(avg_loss, 2),
            "profit_factor":  round(profit_factor, 2),
            "max_drawdown":   round(max_dd, 1),
            "final_balance":  round(balance, 2),
            "return_pct":     round((balance - 10000) / 10000 * 100, 1),
        },
        "params": {
            "atr_sl_mult": atr_sl_mult,
            "atr_tp_mult": atr_tp_mult,
            "min_score":   min_score,
        }
    }


# ── Demo Trade Manager ─────────────────────────────────────────────────────

class DemoTradeManager:

    def get_trades(self) -> list:
        return _load_json(TRADES_FILE, [])

    def open_trade(self, direction: str, entry: float, sl: float, tp1: float,
                   tp2: float, score: int, lot_size: float = 0.1) -> dict:
        trades = self.get_trades()
        trade  = {
            "id":         len(trades) + 1,
            "mode":       "DEMO",
            "direction":  direction,
            "entry":      entry,
            "sl":         sl,
            "tp1":        tp1,
            "tp2":        tp2,
            "lot_size":   lot_size,
            "score":      score,
            "status":     "OPEN",
            "open_date":  datetime.now().isoformat(),
            "close_date": None,
            "close_price":None,
            "pnl":        None,
            "result":     None,
        }
        trades.append(trade)
        _save_json(TRADES_FILE, trades)
        return trade

    def close_trade(self, trade_id: int, close_price: float, result: str) -> dict:
        trades = self.get_trades()
        for t in trades:
            if t["id"] == trade_id and t["status"] == "OPEN":
                sl_dist  = abs(t["entry"] - t["sl"])
                tp_dist  = abs(close_price - t["entry"])
                direction_mult = 1 if t["direction"] == "BUY" else -1
                raw_pnl  = (close_price - t["entry"]) * direction_mult
                pnl_usd  = round(raw_pnl * t["lot_size"] * 100, 2)  # approx for gold
                t.update({
                    "status":      "CLOSED",
                    "close_date":  datetime.now().isoformat(),
                    "close_price": close_price,
                    "pnl":         pnl_usd,
                    "result":      result,
                })
        _save_json(TRADES_FILE, trades)
        return trades

    def get_performance(self) -> dict:
        trades  = [t for t in self.get_trades() if t["status"] == "CLOSED"]
        wins    = [t for t in trades if t["result"] == "TP1"]
        losses  = [t for t in trades if t["result"] == "SL"]
        total_pnl = sum(t.get("pnl", 0) or 0 for t in trades)
        win_rate  = len(wins) / len(trades) * 100 if trades else 0
        return {
            "total_trades": len(trades),
            "wins": len(wins), "losses": len(losses),
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "open_trades": [t for t in self.get_trades() if t["status"] == "OPEN"],
        }

demo_manager = DemoTradeManager()
