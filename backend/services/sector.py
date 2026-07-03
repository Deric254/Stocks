"""
sector.py — Layer 3 (Sector Intelligence) + Layer 4 (Industry Intelligence).

Two distinct data sources feed this, kept separate and clearly labeled:

  1. GLOBAL sector rotation context — US sector SPDR ETFs (XLK, XLF, etc.)
     via stooq.com (keyless). This tells you where GLOBAL capital is
     rotating, which is the constitution's actual ask for Layer 3
     ("momentum, relative strength, capital rotation"). It is NOT
     NSE-specific — the NSE has no free, granular sector index feed,
     so this is an explicitly-labeled global proxy, not a Kenya sector
     index.

  2. LOCAL NSE sector momentum — computed from your own tracked
     tickers' price history (already in DataLoader), grouped by the
     `sector` field already present in NSE_TICKERS. This is real NSE
     data, just coarser (price momentum only, no fundamentals
     aggregation yet) — Layer 4 "industry" ranking within each NSE
     sector reuses this same grouping since NSE doesn't publish
     industry-level granularity below sector either.

NOTE: the stooq portion has NOT been exercised against the live
endpoint in the build sandbox (no network access there). Logic is
unit-verified against mocked response shapes only.
"""

from concurrent.futures import ThreadPoolExecutor
from services.stooq_client import fetch_stooq_closes

# US Sector SPDR ETFs — standard, liquid, free-data-available proxies
# for global sector rotation (constitution's 11 sectors, mapped to the
# closest matching SPDR fund; Real Estate uses XLRE, Comm Services XLC).
SECTOR_ETFS = {
    "Technology":             "xlk.us",
    "Healthcare":              "xlv.us",
    "Financials":              "xlf.us",
    "Energy":                  "xle.us",
    "Utilities":               "xlu.us",
    "Industrials":             "xli.us",
    "Materials":               "xlb.us",
    "Consumer Staples":        "xlp.us",
    "Consumer Discretionary":  "xly.us",
    "Communication Services":  "xlc.us",
    "Real Estate":             "xlre.us",
}

def _momentum_pct(closes: list, lookback_days: int):
    if len(closes) < lookback_days + 1:
        lookback_days = len(closes) - 1
    if lookback_days < 1:
        return None
    start = closes[-(lookback_days + 1)][1]
    end = closes[-1][1]
    if not start:
        return None
    return round((end - start) / start * 100, 2)


# ── Global sector rotation (Layer 3, stooq-sourced) ──────────────────────

def get_global_sector_momentum() -> dict:
    with ThreadPoolExecutor(max_workers=len(SECTOR_ETFS)) as ex:
        futures = {sector: ex.submit(fetch_stooq_closes, symbol, 90) for sector, symbol in SECTOR_ETFS.items()}
        closes_by_sector = {sector: f.result() for sector, f in futures.items()}

    results = {}
    for sector, symbol in SECTOR_ETFS.items():
        closes = closes_by_sector[sector]
        if not closes:
            results[sector] = {
                "available": False, "reason": f"stooq fetch failed for {symbol}",
                "etf_proxy": symbol,
            }
            continue
        results[sector] = {
            "available": True,
            "etf_proxy": symbol,
            "momentum_1m_pct": _momentum_pct(closes, 21),
            "momentum_3m_pct": _momentum_pct(closes, 63),
            "as_of": closes[-1][0],
            "source": "stooq.com",
        }

    available = {k: v for k, v in results.items() if v.get("available")}
    ranked = sorted(available.items(), key=lambda kv: (kv[1].get("momentum_3m_pct") or -999), reverse=True)

    return {
        "available": bool(available),
        "sectors": results,
        "preferred_sectors": [s for s, _ in ranked[:3]],
        "avoided_sectors": [s for s, _ in ranked[-3:]] if len(ranked) >= 3 else [],
        "note": (
            "Global sector rotation via US SPDR sector ETFs (stooq.com), used as "
            "a worldwide capital-flow proxy. The NSE has no free granular sector "
            "index feed, so this complements rather than replaces NSE-local "
            "sector momentum (see 'nse_sectors' in the combined response)."
        ),
    }


# ── NSE-local sector momentum (Layer 3+4, your own tracked tickers) ─────

def get_nse_sector_momentum(nse_tickers: list, loader) -> dict:
    """
    nse_tickers: list of {"ticker":..., "sector":...} dicts (NSE_TICKERS
                 from app.py — already grouped by sector, no industry
                 sub-level exists in this dataset, so Layer 4 "industry"
                 ranking is the same grouping at present).
    loader: DataLoader instance, for get_price_data(ticker).
    """
    by_sector = {}
    for t in nse_tickers:
        by_sector.setdefault(t["sector"], []).append(t["ticker"])

    sector_results = {}
    for sector, tickers in by_sector.items():
        ticker_momenta = []
        for ticker in tickers:
            try:
                df = loader.get_price_data(ticker)
                if df is None or df.empty or len(df) < 22:
                    continue
                closes = list(zip(df.index.astype(str), df["close"].astype(float)))
                m1 = _momentum_pct(closes, 21)
                if m1 is not None:
                    ticker_momenta.append({"ticker": ticker, "momentum_1m_pct": m1})
            except Exception:
                continue

        if not ticker_momenta:
            sector_results[sector] = {
                "available": False,
                "reason": "No tickers in this sector have sufficient price history",
                "tickers_tracked": len(tickers),
            }
            continue

        avg_momentum = round(sum(t["momentum_1m_pct"] for t in ticker_momenta) / len(ticker_momenta), 2)
        ticker_momenta.sort(key=lambda t: t["momentum_1m_pct"], reverse=True)

        sector_results[sector] = {
            "available": True,
            "avg_momentum_1m_pct": avg_momentum,
            "tickers_tracked": len(tickers),
            "tickers_with_data": len(ticker_momenta),
            "leaders": ticker_momenta[:3],
            "laggards": ticker_momenta[-3:] if len(ticker_momenta) > 3 else [],
        }

    available = {k: v for k, v in sector_results.items() if v.get("available")}
    ranked = sorted(available.items(), key=lambda kv: kv[1]["avg_momentum_1m_pct"], reverse=True)

    return {
        "available": bool(available),
        "sectors": sector_results,
        "preferred_sectors": [s for s, _ in ranked[:2]],
        "avoided_sectors": [s for s, _ in ranked[-2:]] if len(ranked) >= 2 else [],
        "note": (
            "Computed from your own tracked NSE price history. Price momentum "
            "only — fundamentals-weighted sector scoring not yet implemented. "
            "Requires uploaded price history per ticker to populate."
        ),
    }


def compute_sector_industry_intelligence(nse_tickers: list, loader) -> dict:
    """Main entry point — combined Layer 3 (global context) + Layer 3/4 (NSE-local)."""
    return {
        "global_sector_rotation": get_global_sector_momentum(),
        "nse_sectors": get_nse_sector_momentum(nse_tickers, loader),
    }
