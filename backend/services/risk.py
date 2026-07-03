"""
risk.py — Layer 9 (Risk Engine) + Layer 11 (Portfolio Intelligence) basics.

Computes Sharpe ratio, Sortino ratio, max drawdown, beta, and a
correlation matrix across portfolio holdings. All inputs come from
data already available in this codebase (the equity curve already
built by analytics.py, and per-ticker price history from DataLoader)
— no new external data source required.

Beta needs a market benchmark. The NSE doesn't have a free, reliably
fetchable index feed in this codebase yet, so as an explicit, declared
approximation we use an equal-weighted basket of all tracked NSE
tickers as a market proxy. This is flagged in every beta output so
it's never mistaken for a true NASI beta — swap in real NASI data
later (paid phase) without changing the function signature.

Risk-free rate defaults to ~13% (approx. Kenya 91-day T-bill, an
explicit assumption, not hidden) — pass a different rate if you have
a more current figure.
"""

import math
import pandas as pd
import numpy as np

TRADING_DAYS_PER_YEAR = 252
DEFAULT_RISK_FREE_ANNUAL = 0.13


def _safe(val, default=None):
    if val is None:
        return default
    try:
        f = float(val)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return default


def _daily_returns(values: list) -> np.ndarray:
    clean = [v for v in values if _safe(v) is not None and v > 0]
    if len(clean) < 2:
        return np.array([])
    arr = np.array(clean, dtype=float)
    return (arr[1:] - arr[:-1]) / arr[:-1]


# ── Sharpe / Sortino ──────────────────────────────────────────────────────

def sharpe_ratio(values: list, risk_free_annual: float = DEFAULT_RISK_FREE_ANNUAL) -> dict:
    returns = _daily_returns(values)
    if len(returns) < 10:
        return {"available": False, "reason": "Need 10+ data points for a meaningful Sharpe ratio"}

    rf_daily = risk_free_annual / TRADING_DAYS_PER_YEAR
    excess = returns - rf_daily
    std = excess.std(ddof=1)
    if std == 0:
        return {"available": False, "reason": "Zero volatility — Sharpe ratio undefined"}

    daily_sharpe = excess.mean() / std
    annualized = daily_sharpe * math.sqrt(TRADING_DAYS_PER_YEAR)
    return {
        "available": True,
        "value": round(float(annualized), 3),
        "risk_free_annual_used": risk_free_annual,
        "interpretation": (
            "Strong" if annualized > 1.0 else
            "Acceptable" if annualized > 0.5 else
            "Weak" if annualized > 0 else "Poor"
        ),
    }


def sortino_ratio(values: list, risk_free_annual: float = DEFAULT_RISK_FREE_ANNUAL) -> dict:
    returns = _daily_returns(values)
    if len(returns) < 10:
        return {"available": False, "reason": "Need 10+ data points for a meaningful Sortino ratio"}

    rf_daily = risk_free_annual / TRADING_DAYS_PER_YEAR
    excess = returns - rf_daily
    downside = excess[excess < 0]
    if len(downside) == 0:
        return {"available": False, "reason": "No downside periods observed — Sortino undefined"}

    downside_std = downside.std(ddof=1) if len(downside) > 1 else abs(downside[0])
    if downside_std == 0:
        return {"available": False, "reason": "Zero downside deviation — Sortino undefined"}

    daily_sortino = excess.mean() / downside_std
    annualized = daily_sortino * math.sqrt(TRADING_DAYS_PER_YEAR)
    return {
        "available": True,
        "value": round(float(annualized), 3),
        "risk_free_annual_used": risk_free_annual,
        "interpretation": (
            "Strong" if annualized > 1.5 else
            "Acceptable" if annualized > 0.75 else
            "Weak" if annualized > 0 else "Poor"
        ),
    }


# ── Max drawdown ──────────────────────────────────────────────────────────

def max_drawdown(values: list) -> dict:
    clean = [v for v in values if _safe(v) is not None and v > 0]
    if len(clean) < 2:
        return {"available": False, "reason": "Insufficient data for drawdown calculation"}

    arr = np.array(clean, dtype=float)
    running_max = np.maximum.accumulate(arr)
    drawdowns = (arr - running_max) / running_max
    trough_idx = int(np.argmin(drawdowns))
    peak_idx = int(np.argmax(arr[:trough_idx + 1])) if trough_idx > 0 else 0

    return {
        "available": True,
        "max_drawdown_pct": round(float(drawdowns.min()) * 100, 2),
        "peak_index": peak_idx,
        "trough_index": trough_idx,
        "current_drawdown_pct": round(float(drawdowns[-1]) * 100, 2),
    }


# ── Beta (vs equal-weighted NSE basket proxy) ─────────────────────────────

def beta_vs_benchmark(asset_returns: np.ndarray, benchmark_returns: np.ndarray) -> dict:
    n = min(len(asset_returns), len(benchmark_returns))
    if n < 10:
        return {"available": False, "reason": "Need 10+ overlapping return periods for beta"}

    a = asset_returns[-n:]
    b = benchmark_returns[-n:]
    bench_var = np.var(b, ddof=1)
    if bench_var == 0:
        return {"available": False, "reason": "Benchmark has zero variance — beta undefined"}

    cov = np.cov(a, b, ddof=1)[0][1]
    beta = cov / bench_var

    return {
        "available": True,
        "value": round(float(beta), 3),
        "benchmark": "Equal-weighted basket of tracked NSE tickers (approximation — not true NASI beta)",
        "interpretation": (
            "More volatile than market" if beta > 1.2 else
            "In line with market" if beta >= 0.8 else
            "Less volatile than market"
        ),
    }


# ── Correlation matrix across holdings ───────────────────────────────────

def correlation_matrix(price_series_by_ticker: dict) -> dict:
    """
    price_series_by_ticker: {ticker: pd.Series of close prices, datetime index}
    Returns a correlation matrix of daily returns. Tickers with
    insufficient history are dropped from the matrix and listed
    separately rather than silently zero-filled.
    """
    returns_by_ticker = {}
    excluded = []
    for ticker, series in price_series_by_ticker.items():
        if series is None or len(series) < 10:
            excluded.append(ticker)
            continue
        rets = series.pct_change().dropna()
        if len(rets) < 10:
            excluded.append(ticker)
            continue
        returns_by_ticker[ticker] = rets

    if len(returns_by_ticker) < 2:
        return {
            "available": False,
            "reason": "Need 2+ holdings with sufficient price history for a correlation matrix",
            "excluded": excluded,
        }

    df = pd.DataFrame(returns_by_ticker).dropna(how="all")
    corr = df.corr().round(3)
    corr = corr.where(pd.notna(corr), None)

    return {
        "available": True,
        "tickers": list(corr.columns),
        "matrix": corr.values.tolist(),
        "excluded": excluded,
    }


# ── Main entry point ──────────────────────────────────────────────────────

def compute_portfolio_risk(equity_curve: list, price_series_by_ticker: dict,
                            benchmark_values: list = None,
                            risk_free_annual: float = DEFAULT_RISK_FREE_ANNUAL,
                            holdings: list = None, sector_by_ticker: dict = None) -> dict:
    """
    equity_curve: [{"date": ..., "value": ...}, ...] from analytics.py
    price_series_by_ticker: {ticker: pd.Series} for each current holding
    benchmark_values: optional list of equal-weighted basket values
                       (same length cadence as equity_curve); if not
                       supplied, beta is skipped per-holding.
    holdings / sector_by_ticker: optional — if supplied, adds Layer 11
                       diversification metrics and portfolio health score.
    """
    values = [pt.get("value") for pt in (equity_curve or [])]

    sharpe = sharpe_ratio(values, risk_free_annual)
    sortino = sortino_ratio(values, risk_free_annual)
    mdd = max_drawdown(values)
    corr = correlation_matrix(price_series_by_ticker)

    betas = {}
    if benchmark_values:
        bench_returns = _daily_returns(benchmark_values)
        for ticker, series in price_series_by_ticker.items():
            if series is None or len(series) < 11:
                betas[ticker] = {"available": False, "reason": "Insufficient price history"}
                continue
            asset_returns = series.pct_change().dropna().values
            betas[ticker] = beta_vs_benchmark(asset_returns, bench_returns)
    else:
        betas = {"available": False, "reason": "No benchmark series supplied"}

    result = {
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown": mdd,
        "beta_by_holding": betas,
        "correlation_matrix": corr,
        "assumptions": {
            "risk_free_annual": risk_free_annual,
            "benchmark_note": (
                "Beta uses an equal-weighted basket of all tracked NSE "
                "tickers as a market proxy, since no free NASI index feed "
                "is wired up yet."
            ),
        },
    }

    if holdings is not None:
        div = diversification_metrics(holdings, sector_by_ticker or {})
        health = portfolio_health_score(sharpe, mdd, div)
        result["diversification"] = div
        result["portfolio_health"] = health

    return result


# ── Layer 11 completion: diversification & portfolio health ─────────────

def diversification_metrics(holdings: list, sector_by_ticker: dict) -> dict:
    """
    holdings: [{"ticker":..., "current_price":..., "quantity":...}, ...]
    sector_by_ticker: {ticker: sector_name}

    Computes sector exposure (concentration) and a Herfindahl-Hirschman
    Index (HHI) for diversification — standard, transparent, reproducible
    (no proprietary 'diversification score' black box).
    """
    if not holdings:
        return {"available": False, "reason": "No holdings"}

    values = {}
    total = 0.0
    for h in holdings:
        v = (h.get("current_price") or 0) * (h.get("quantity") or 0)
        values[h["ticker"]] = v
        total += v

    if total <= 0:
        return {"available": False, "reason": "Zero portfolio value"}

    # Sector exposure — sector_by_ticker is keyed by base ticker (no
    # exchange suffix), but holdings tickers carry suffixes like
    # ".NR"/".NRO" — strip before lookup so it actually matches.
    sector_value = {}
    for ticker, v in values.items():
        base = ticker.split(".")[0]
        sector = sector_by_ticker.get(ticker) or sector_by_ticker.get(base, "Unknown")
        sector_value[sector] = sector_value.get(sector, 0) + v

    sector_pct = {s: round(v / total * 100, 1) for s, v in sector_value.items()}
    ticker_pct = {t: round(v / total * 100, 1) for t, v in values.items()}

    # HHI on tickers (0-10000 scale; <1500 = diversified, 1500-2500 = moderate, >2500 = concentrated)
    hhi_ticker = sum((pct) ** 2 for pct in ticker_pct.values())
    hhi_sector = sum((pct) ** 2 for pct in sector_pct.values())

    def hhi_label(hhi):
        return "Concentrated" if hhi > 2500 else "Moderate" if hhi > 1500 else "Diversified"

    largest_position = max(ticker_pct.items(), key=lambda kv: kv[1]) if ticker_pct else (None, 0)
    largest_sector = max(sector_pct.items(), key=lambda kv: kv[1]) if sector_pct else (None, 0)

    return {
        "available": True,
        "num_holdings": len(holdings),
        "num_sectors": len(sector_value),
        "sector_exposure_pct": sector_pct,
        "ticker_exposure_pct": ticker_pct,
        "hhi_by_ticker": round(hhi_ticker, 1),
        "hhi_by_ticker_label": hhi_label(hhi_ticker),
        "hhi_by_sector": round(hhi_sector, 1),
        "hhi_by_sector_label": hhi_label(hhi_sector),
        "largest_position": {"ticker": largest_position[0], "pct": largest_position[1]},
        "largest_sector": {"sector": largest_sector[0], "pct": largest_sector[1]},
        "concentration_warning": (
            f"{largest_position[0]} alone is {largest_position[1]}% of the portfolio — "
            "single-position concentration risk." if largest_position[1] > 30 else None
        ),
    }


def portfolio_health_score(sharpe: dict, max_dd: dict, diversification: dict) -> dict:
    """
    Composite 0-100 health score combining risk-adjusted return,
    drawdown control, and diversification — transparent weighted
    average, not a black box. Missing components reduce coverage,
    never silently default to a neutral/zero score.
    """
    components = {}
    weight_used = 0.0
    score = 0.0

    if sharpe.get("available"):
        # Sharpe of 1.5+ -> full marks; 0 or below -> 0
        s = max(0, min(sharpe["value"] / 1.5, 1)) * 100
        components["sharpe"] = round(s, 1)
        score += s * 0.4
        weight_used += 0.4

    if max_dd.get("available"):
        # 0% drawdown -> full marks; -50%+ -> 0
        dd = max_dd["max_drawdown_pct"]  # negative number
        d = max(0, min(1, 1 - abs(dd) / 50)) * 100
        components["drawdown_control"] = round(d, 1)
        score += d * 0.35
        weight_used += 0.35

    if diversification.get("available"):
        # HHI by sector: 0 (perfectly diversified) -> 100; 10000 (single sector) -> 0
        hhi = diversification["hhi_by_sector"]
        div = max(0, min(1, 1 - hhi / 10000)) * 100
        components["diversification"] = round(div, 1)
        score += div * 0.25
        weight_used += 0.25

    if weight_used == 0:
        return {"available": False, "reason": "Insufficient data across all components"}

    final = round(score / weight_used, 1)
    label = "Excellent" if final >= 75 else "Good" if final >= 55 else "Fair" if final >= 35 else "Needs Attention"

    # Hard concentration cap — a weighted average can dilute away real
    # concentration risk (e.g. Sharpe/drawdown look "perfect" on a
    # single holding with only days of history, masking that one bad
    # earnings report could wipe out the whole portfolio). For a
    # system used with real capital, this must never be labeled
    # Excellent or Good regardless of what the other components say.
    concentration_capped = False
    if diversification.get("available"):
        largest_pct = diversification.get("largest_position", {}).get("pct", 0)
        if largest_pct >= 70:
            if label in ("Excellent", "Good"):
                label = "Fair"
                concentration_capped = True
        elif largest_pct >= 50 and label == "Excellent":
            label = "Good"
            concentration_capped = True

    result = {
        "available": True,
        "score": final,
        "label": label,
        "components": components,
        "coverage": f"{len(components)}/3 components (sharpe, drawdown control, diversification)",
        "concentration_capped": concentration_capped,
    }
    if concentration_capped:
        result["cap_note"] = (
            "Label capped due to single-position concentration risk — the raw "
            "weighted score can look artificially strong on a new or "
            "single-holding portfolio where Sharpe/drawdown have too little "
            "history to mean much yet."
        )
    return result
