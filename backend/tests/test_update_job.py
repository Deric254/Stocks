"""Regression tests for the 'Update Data' button: must finish fast, stay consistent, never fake data."""
import time
from datetime import datetime


def _mgr(tmp_path, monkeypatch):
    import services.csv_data_manager as cdm
    monkeypatch.setattr(cdm, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cdm, "PRICES_CSV", tmp_path / "prices_manual.csv")
    monkeypatch.setattr(cdm, "PRICES_HISTORY", tmp_path / "prices_history_manual.csv")
    monkeypatch.setattr(cdm, "FUNDAMENTALS_CSV", tmp_path / "fundamentals_manual.csv")
    monkeypatch.setattr(cdm, "META_JSON", tmp_path / "config.json")
    return cdm.CSVDataManager()


def _patch(monkeypatch, quote_fn, bulk=None):
    monkeypatch.setattr("services.nse_scraper.fetch_live_quote", quote_fn)
    monkeypatch.setattr("services.nse_scraper.get_all_prices", lambda: bulk or {})


def test_blocked_source_stops_fast_and_keeps_data(tmp_path, monkeypatch):
    mgr = _mgr(tmp_path, monkeypatch)
    mgr._fundamentals["T0"] = {"ticker": "T0", "eps": 5.0, "pe": 10.0, "data_source": "real_upload"}
    calls = []

    def blocked(base):
        calls.append(base)
        time.sleep(0.05)
        return {}, "HTTP 403"

    _patch(monkeypatch, blocked)
    tickers = [{"ticker": f"T{i}"} for i in range(40)]
    report = mgr.refresh_all_data(tickers, workers=2)
    assert len(calls) < 15, "circuit breaker must stop hammering a blocked source"
    assert report["status"] == "no_live_data"
    assert any("not reachable" in w for w in report["warnings"])
    assert mgr._fundamentals["T0"]["pe"] == 10.0


def test_deadline_returns_even_if_sources_hang(tmp_path, monkeypatch):
    mgr = _mgr(tmp_path, monkeypatch)
    mgr._fundamentals["SLOW"] = {"ticker": "SLOW", "eps": 5.0, "pe": 10.0, "data_source": "real_upload"}

    def slow(base):
        time.sleep(3)
        return {"price": 50.0}, None

    _patch(monkeypatch, slow)
    t0 = time.monotonic()
    report = mgr.refresh_all_data([{"ticker": "SLOW"}], deadline_s=1, workers=1)
    assert time.monotonic() - t0 < 2.5
    assert report["fundamentals"]["timed_out"] == ["SLOW"]
    assert mgr._fundamentals["SLOW"]["pe"] == 10.0


def test_live_fills_gaps_but_never_overwrites_researched_values(tmp_path, monkeypatch):
    mgr = _mgr(tmp_path, monkeypatch)
    mgr._fundamentals["EQTY"] = {"ticker": "EQTY", "eps": 19.0, "pe": 3.0, "dividends": 5.0,
                                 "data_source": "real_upload"}
    _patch(monkeypatch, lambda base: ({"price": 76.0, "eps": 999.0, "pe": 1.0,
                                       "market_cap": 2.8e11, "source": "afx.kwayisi.org"}, None))
    mgr.refresh_all_data([{"ticker": "EQTY"}])
    row = mgr._fundamentals["EQTY"]
    assert row["eps"] == 19.0, "researched EPS must not be replaced by another source's EPS"
    assert row["market_cap"] == 2.8e11, "empty field is filled from live"
    assert row["pe"] == round(76.0 / 19.0, 2), "PE recomputed from fresh price and the SAME EPS"
    assert row["dividend_yield"] == round(5.0 / 76.0, 4)
    assert row["data_source"].startswith("real_upload")
    assert mgr._prices["EQTY"]["price"] == 76.0


def test_unchanged_data_is_not_counted_as_improvement(tmp_path, monkeypatch):
    mgr = _mgr(tmp_path, monkeypatch)
    mgr._fundamentals["EQTY"] = {"ticker": "EQTY", "eps": 19.0, "pe": 4.0, "data_source": "real_upload"}
    _patch(monkeypatch, lambda base: ({}, "HTTP 429"))
    report = mgr.refresh_all_data([{"ticker": "EQTY"}])
    assert report["fundamentals"]["tickers_improved"] == 0
    assert mgr._fundamentals["EQTY"]["data_source"] == "real_upload"


def test_stub_and_stale_prices_never_recorded_as_today(tmp_path, monkeypatch):
    mgr = _mgr(tmp_path, monkeypatch)
    live = {
        "STUB": {"price": 10.0, "source": "manual_stub", "stale": True, "updated_at": "manual"},
        "OLD":  {"price": 11.0, "source": "kenyanstocks.com", "updated_at": "2026-01-01T09:00:00"},
        "GOOD": {"price": 12.0, "source": "kenyanstocks.com", "updated_at": datetime.now().isoformat()},
    }
    res = mgr.snapshot_daily_prices(live)
    assert res["added"] == ["GOOD"]
    assert set(res["skipped_stale"]) == {"STUB", "OLD"}


def test_afx_parser_reads_labels_not_opening_price():
    from services.nse_scraper import _parse_afx_html
    html = """<p>The current share price of Equity Group Holdings Plc (EQTY) is KES 76.25.</p>
    <table><tr><td>Opening Price</td><td>75.00</td></tr>
    <tr><td>Earnings Per Share</td><td>19.07</td></tr><tr><td>Price/Earning Ratio</td><td>4.00</td></tr>
    <tr><td>Dividend Per Share</td><td>5.75</td></tr><tr><td>Dividend Yield</td><td>7.5%</td></tr>
    <tr><td>Shares Outstanding</td><td>3.77B</td></tr><tr><td>Market Capitalization</td><td>287.4B</td></tr></table>"""
    d = _parse_afx_html(html)
    assert d["price"] == 76.25, "must be the current price, not Opening Price"
    assert d["eps"] == 19.07 and d["pe"] == 4.0 and d["dividends"] == 5.75
    assert abs(d["dividend_yield"] - 0.075) < 1e-9
    assert d["market_cap"] == 287.4e9
    blank = html.replace("<td>19.07</td>", "<td></td>")
    assert "eps" not in _parse_afx_html(blank), "blank on the page stays blank"
