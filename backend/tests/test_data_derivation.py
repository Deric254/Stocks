"""
test_data_derivation.py — the arithmetic gap-filling logic behind the
"Update Data" button. Every derived figure must trace to real values
already present in the same row; a value with nothing real to derive
it from must stay honestly empty, never fabricated.

Run with: pytest tests/test_data_derivation.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.csv_data_manager import _derive_fundamentals_row


def test_margin_derived_from_net_income_and_revenue():
    row, derived = _derive_fundamentals_row({"net_income": 1000, "revenue": 4000})
    assert row["margin"] == 0.25
    assert "margin" in derived


def test_eps_derived_from_price_and_pe():
    row, derived = _derive_fundamentals_row({"price": 100, "pe": 10})
    assert row["eps"] == 10.0
    assert "eps" in derived


def test_pe_derived_from_price_and_eps_reverse_direction():
    row, derived = _derive_fundamentals_row({"price": 100, "eps": 20})
    assert row["pe"] == 5.0
    assert "pe" in derived


def test_negative_computed_pe_is_blanked_not_shown():
    """A loss-making company's price/eps division produces a negative
    PE, which isn't a meaningful multiple - must stay blank, not be
    presented as a real number."""
    row, derived = _derive_fundamentals_row({"price": 100, "eps": -5})
    assert "pe" not in derived
    assert row.get("pe") in (None, "")


def test_anomalous_dividend_yield_over_100pct_is_rejected():
    """dividends > price produces a >100% yield, which is almost
    certainly a data error (mismatched units, wrong currency, etc.) -
    must not be presented as a valid figure."""
    row, derived = _derive_fundamentals_row({"price": 10, "dividends": 50})
    assert "dividend_yield" not in derived


def test_dividends_derived_from_yield_and_price_reverse_direction():
    row, derived = _derive_fundamentals_row({"price": 100, "dividend_yield": 0.05})
    assert row["dividends"] == 5.0
    assert "dividends" in derived


def test_never_overwrites_an_existing_real_value():
    """The whole point of this function is to fill GAPS - an existing
    real value, even one that could also be arithmetically derived
    from other fields, must never be silently replaced."""
    row, derived = _derive_fundamentals_row({"price": 100, "pe": 10, "eps": 999})
    assert row["eps"] == 999
    assert "eps" not in derived


def test_data_source_annotated_with_audit_trail():
    """Every derived value must be traceable - never a silent,
    unexplained number appearing where there was none before."""
    row, derived = _derive_fundamentals_row({
        "net_income": 1000, "revenue": 4000, "data_source": "my_upload",
    })
    assert "my_upload" in row["data_source"]
    assert "derived this update: margin" in row["data_source"]


def test_nothing_to_derive_from_stays_empty():
    """If there's genuinely no real value anywhere in the row to
    derive a field from, it must stay empty - never fabricated."""
    row, derived = _derive_fundamentals_row({"ticker": "NODATA"})
    assert derived == []
    assert row.get("margin") in (None, "")
    assert row.get("eps") in (None, "")


def test_zero_revenue_does_not_cause_division_by_zero():
    """Defensive: a real-world zero/missing revenue must not crash
    the derivation, just skip that field."""
    row, derived = _derive_fundamentals_row({"net_income": 1000, "revenue": 0})
    assert "margin" not in derived


def test_refresh_all_data_never_lets_scraper_seed_fallback_overwrite_real_data(tmp_path, monkeypatch):
    """
    Regression guard for a critical bug found via an actual end-to-end
    test with real uploaded data: nse_scraper.get_fundamentals() has
    its own internal Tier-3 fallback that returns old, possibly-fake
    placeholder data (tagged data_source="seed_fy2024") when live
    scraping fails. refresh_all_data() must never treat that as
    genuine live data - doing so silently overwrote real, correctly-
    uploaded EPS/history data with old fabricated numbers the first
    time this was tested against the actual codebase.
    """
    import services.csv_data_manager as cdm

    orig_data_dir = cdm.DATA_DIR
    cdm.DATA_DIR = tmp_path
    cdm.PRICES_CSV = tmp_path / "prices_manual.csv"
    cdm.PRICES_HISTORY = tmp_path / "prices_history_manual.csv"
    cdm.FUNDAMENTALS_CSV = tmp_path / "fundamentals_manual.csv"
    cdm.META_JSON = tmp_path / "config.json"

    try:
        mgr = cdm.CSVDataManager()
        # seed real, correct data directly into memory
        mgr._fundamentals["EQTY"] = {
            "ticker": "EQTY", "eps": 19.07, "net_income_history": [],
            "data_source": "real_upload", "revenue": 1000, "net_income": 300,
            "margin": 0.3, "pe": 3.94,  # already set - isolates this test to the
                                         # seed-rejection behavior specifically,
                                         # with no legitimate derivation opportunity
                                         # left to conflate with the "improved" count
        }
        # deliberately no price entry - removes the PE-from-price/eps
        # derivation opportunity too, for the same isolation reason
        # (no price entry - see comment above)

        # simulate the scraper's own seed-fallback tier firing (as it
        # does whenever every live source is blocked/unreachable)
        def fake_scraper_get_fundamentals(base):
            return {
                "ticker": base, "eps": 999.0, "net_income_history": [1, 2, 3],
                "data_source": "seed_fy2024",  # the exact tag that must be rejected
            }

        monkeypatch.setattr("services.nse_scraper.get_fundamentals", fake_scraper_get_fundamentals)
        monkeypatch.setattr("services.nse_scraper.get_all_prices", lambda: {})

        report = mgr.refresh_all_data([{"ticker": "EQTY", "sector": "Banking"}])

        eqty_after = mgr._fundamentals["EQTY"]
        assert eqty_after["eps"] == 19.07, "real EPS must survive - seed fallback must never override it"
        assert eqty_after["net_income_history"] == [], "real empty history must survive, not be replaced by fake seed history"
        assert report["fundamentals"]["tickers_improved"] == 0, "nothing genuine changed - seed-tagged data must not count as improvement"
    finally:
        cdm.DATA_DIR = orig_data_dir
