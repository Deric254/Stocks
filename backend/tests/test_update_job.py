"""Regression tests for the 'Update Data' button: must finish, stay consistent, never fake data."""
import time
import pytest


def _mgr(tmp_path, monkeypatch):
    import services.csv_data_manager as cdm
    monkeypatch.setattr(cdm, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cdm, "PRICES_CSV", tmp_path / "prices_manual.csv")
    monkeypatch.setattr(cdm, "PRICES_HISTORY", tmp_path / "prices_history_manual.csv")
    monkeypatch.setattr(cdm, "FUNDAMENTALS_CSV", tmp_path / "fundamentals_manual.csv")
    monkeypatch.setattr(cdm, "META_JSON", tmp_path / "config.json")
    return cdm.CSVDataManager()


def test_slow_tickers_hit_deadline_and_keep_existing_data(tmp_path, monkeypatch):
    mgr = _mgr(tmp_path, monkeypatch)
    mgr._fundamentals["SLOW"] = {"ticker": "SLOW", "eps": 5.0, "pe": 10.0, "data_source": "real_upload"}

    def slow(base, allow_price_fetch=True):
        time.sleep(3)
        return {"ticker": base, "pe": 99.0, "data_source": "afx.kwayisi.org"}

    monkeypatch.setattr("services.nse_scraper.get_fundamentals", slow)
    monkeypatch.setattr("services.nse_scraper.get_all_prices", lambda: {})
    t0 = time.monotonic()
    report = mgr.refresh_all_data([{"ticker": "SLOW"}], deadline_s=1, workers=2)
    assert time.monotonic() - t0 < 2.5, "must return at the deadline, not wait for slow sources"
    assert report["fundamentals"]["timed_out"] == ["SLOW"]
    assert mgr._fundamentals["SLOW"]["pe"] == 10.0, "timed-out ticker keeps its existing data"
    assert report["status"] in ("partial", "no_live_data")


def test_live_metadata_does_not_overwrite_or_count_as_improvement(tmp_path, monkeypatch):
    mgr = _mgr(tmp_path, monkeypatch)
    mgr._fundamentals["EQTY"] = {"ticker": "EQTY", "eps": 19.0, "pe": 4.0, "margin": 0.3,
                                 "data_source": "real_upload", "last_update": "2026-04-07"}
    # live returns only metadata + values identical to what we already have
    monkeypatch.setattr("services.nse_scraper.get_fundamentals",
                        lambda base, allow_price_fetch=True: {"ticker": base, "eps": 19.0, "pe": 4.0,
                                                              "data_source": "afx.kwayisi.org",
                                                              "last_update": "2026-10-01T10:00", "fetch_ok": True})
    monkeypatch.setattr("services.nse_scraper.get_all_prices", lambda: {})
    report = mgr.refresh_all_data([{"ticker": "EQTY"}])
    assert report["fundamentals"]["tickers_improved"] == 0
    assert mgr._fundamentals["EQTY"]["data_source"] == "real_upload"


def test_stub_and_stale_prices_never_recorded_as_today(tmp_path, monkeypatch):
    from datetime import datetime
    mgr = _mgr(tmp_path, monkeypatch)
    live = {
        "STUB": {"price": 10.0, "source": "manual_stub", "stale": True, "updated_at": "manual"},
        "OLD":  {"price": 11.0, "source": "kenyanstocks.com", "updated_at": "2026-01-01T09:00:00"},
        "GOOD": {"price": 12.0, "source": "kenyanstocks.com", "updated_at": datetime.now().isoformat()},
    }
    res = mgr.snapshot_daily_prices(live)
    assert res["added"] == ["GOOD"]
    assert set(res["skipped_stale"]) == {"STUB", "OLD"}
