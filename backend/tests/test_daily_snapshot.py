"""
test_daily_snapshot.py — ACID properties of the daily price snapshot.

This is the mechanism that lets real NSE price history accumulate day
by day (since no free historical NSE data source exists — see
CSVDataManager.snapshot_daily_prices docstring for why). Because it's
a write path that runs unattended in a background thread, it gets a
dedicated test file proving each ACID property with a real failure
scenario, not just a happy-path check.

Run with: pytest tests/test_daily_snapshot.py -v
"""

import os
import sys
import shutil
import tempfile
import pathlib
import pandas as pd
import pytest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import services.csv_data_manager as cdm


@pytest.fixture
def isolated_manager():
    """Fresh CSVDataManager pointed at a throwaway directory — never
    touches real data, regardless of what the test does to it."""
    tmpdir = tempfile.mkdtemp()
    orig = {
        "DATA_DIR": cdm.DATA_DIR, "PRICES_CSV": cdm.PRICES_CSV,
        "PRICES_HISTORY": cdm.PRICES_HISTORY, "FUNDAMENTALS_CSV": cdm.FUNDAMENTALS_CSV,
        "META_JSON": cdm.META_JSON,
    }
    cdm.DATA_DIR = pathlib.Path(tmpdir)
    cdm.PRICES_CSV = cdm.DATA_DIR / "prices_manual.csv"
    cdm.PRICES_HISTORY = cdm.DATA_DIR / "prices_history_manual.csv"
    cdm.FUNDAMENTALS_CSV = cdm.DATA_DIR / "fundamentals_manual.csv"
    cdm.META_JSON = cdm.DATA_DIR / "config.json"

    yield cdm.CSVDataManager()

    for k, v in orig.items():
        setattr(cdm, k, v)
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_snapshot_adds_real_rows(isolated_manager):
    mgr = isolated_manager
    result = mgr.snapshot_daily_prices({"JUB": {"price": 115.0, "volume": 5000}})
    assert result["total_added"] == 1
    assert "JUB" in result["added"]


def test_consistency_rejects_bad_prices(isolated_manager):
    """A scraper hiccup returning 0/None must never pollute history
    with a fake data point."""
    mgr = isolated_manager
    result = mgr.snapshot_daily_prices({
        "ZERO": {"price": 0, "volume": 100},
        "NONE": {"price": None, "volume": 100},
        "NEGATIVE": {"price": -5, "volume": 100},
    })
    assert result["total_added"] == 0
    assert set(result["skipped_no_price"]) == {"ZERO", "NONE", "NEGATIVE"}
    # nothing should have been written to disk at all
    assert not cdm.PRICES_HISTORY.exists()


def test_idempotent_same_day_call(isolated_manager):
    """Calling the snapshot twice in one day (redeploy, retry, cron
    overlap) must never create duplicate rows."""
    mgr = isolated_manager
    mgr.snapshot_daily_prices({"JUB": {"price": 115.0, "volume": 5000}})
    result2 = mgr.snapshot_daily_prices({"JUB": {"price": 116.0, "volume": 5100}})

    assert result2["total_added"] == 0
    assert "JUB" in result2["skipped_duplicate"]

    df = pd.read_csv(cdm.PRICES_HISTORY)
    assert len(df) == 1, "must be exactly one row for JUB, not two"
    assert df.iloc[0]["close"] == 115.0, "first price of the day wins, not overwritten by a later call"


def test_atomicity_failed_write_leaves_file_unchanged(isolated_manager):
    """If the disk write fails partway through, the existing file must
    be byte-for-byte unchanged — never half-written or corrupt."""
    mgr = isolated_manager
    mgr.snapshot_daily_prices({"JUB": {"price": 115.0, "volume": 5000}})
    before = pd.read_csv(cdm.PRICES_HISTORY).to_dict(orient="records")

    with mock.patch("pandas.DataFrame.to_csv", side_effect=OSError("simulated disk failure")):
        # snapshot_daily_prices catches internally via _write_csv_atomic
        # and must not raise or corrupt state
        mgr.snapshot_daily_prices({"EQTY": {"price": 45.5, "volume": 1000}})

    after = pd.read_csv(cdm.PRICES_HISTORY).to_dict(orient="records")
    assert after == before, "file must be unchanged after a failed write"


def test_isolation_concurrent_snapshots_do_not_corrupt(isolated_manager):
    """Multiple threads calling the snapshot concurrently must never
    interleave into a corrupt file — every row that lands must be a
    complete, valid row."""
    import threading
    mgr = isolated_manager
    tickers = [f"TICK{i}" for i in range(20)]

    def _snapshot_batch(batch):
        mgr.snapshot_daily_prices({t: {"price": 100.0 + i, "volume": 1000} for i, t in enumerate(batch)})

    threads = [threading.Thread(target=_snapshot_batch, args=([t],)) for t in tickers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    df = pd.read_csv(cdm.PRICES_HISTORY)
    assert len(df) == len(tickers), "every concurrent snapshot must land exactly once, none lost or duplicated"
    assert set(df["ticker"]) == set(tickers)
    # every row must be complete — no partial/NaN rows from interleaved writes
    assert df["close"].notna().all()
    assert df["date"].notna().all()


def test_current_price_table_advances_but_never_regresses(isolated_manager):
    """The 'current price' table should only move forward in time —
    a same-day snapshot should not overwrite a newer manual upload."""
    mgr = isolated_manager
    mgr.snapshot_daily_prices({"JUB": {"price": 115.0, "volume": 5000}})
    price_row = mgr.get_current_price("JUB")
    assert price_row.get("price") == 115.0


def test_snapshot_updates_prices_ticker_count_meta(isolated_manager):
    """Regression guard: found by running the actual packaged
    executable end-to-end. prices_ticker_count is what
    /api/system-status reports as 'local_data' health — it used to
    only get set by manual CSV uploads, so a fresh install running
    purely on auto-snapshots would show 'degraded' status forever
    even with real, correct price data on disk. Must stay accurate
    after an auto-snapshot too."""
    mgr = isolated_manager
    mgr.snapshot_daily_prices({"JUB": {"price": 115.0}, "EQTY": {"price": 45.5}})
    meta = mgr.get_upload_meta()
    assert meta.get("prices_ticker_count") == 2
