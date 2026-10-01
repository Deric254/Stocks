"""Bulk price parser + price cache freshness (nse_scraper)."""
from datetime import datetime, timedelta
from unittest import mock

from services import nse_scraper as s

PRICE_TABLE = """<table><thead><tr><th>Symbol</th><th>Company</th><th>Sector</th>
<th>Price (KES)</th><th>Change</th><th>Volume</th></tr></thead><tbody>
<tr><td><a href="/stock/SCOM">SCOM</a></td><td>Safaricom</td><td>Telecom</td><td>28.50</td><td>+1.2%</td><td>1.2M</td></tr>
<tr><td><a href="/stock/EQTY">EQTY</a></td><td>Equity</td><td>Banking</td><td>1,250.00</td><td>-0.5%</td><td>850K</td></tr>
</tbody></table>"""
SUMMARY = "<table><tr><th>Index</th><th>Value</th></tr><tr><td>NASI</td><td>180</td></tr></table>"


def _scrape(html):
    s.LAST_STATUS.clear()
    with mock.patch.object(s, "_get_ex", lambda url, **k: (html, None)):
        return s._scrape_kenyanstocks_bulk()


def test_parses_price_change_volume():
    r = _scrape(PRICE_TABLE)
    assert r["SCOM"] == {"price": 28.5, "change_pct": 1.2, "volume": 1200000, "source": "kenyanstocks.com"}
    assert r["EQTY"]["price"] == 1250.0 and r["EQTY"]["volume"] == 850000
    assert s.LAST_STATUS["kenyanstocks.com"] == "ok - 2 stocks read"


def test_finds_price_table_even_when_not_first_on_page():
    assert set(_scrape(SUMMARY + PRICE_TABLE)) == {"SCOM", "EQTY"}


def test_price_change_column_is_never_taken_as_price():
    html = PRICE_TABLE.replace("<th>Change</th>", "<th>Price Change %</th>")
    assert _scrape(html)["SCOM"]["price"] == 28.5


def test_kes_denominated_column_after_price_does_not_override_price():
    html = PRICE_TABLE.replace("<th>Volume</th>", "<th>Volume</th><th>Market Cap (KES)</th>")
    assert _scrape(html)["SCOM"]["price"] == 28.5


def test_no_price_header_is_reported_not_guessed():
    r = _scrape(SUMMARY)
    assert r == {} and "no table has a Price column" in s.LAST_STATUS["kenyanstocks.com"]


def test_no_table_reports_javascript_page():
    assert _scrape("<html><body><div id=app></div></body></html>") == {}
    assert "JavaScript" in s.LAST_STATUS["kenyanstocks.com"]


def test_price_table_with_unreadable_rows_is_not_reported_ok():
    html = "<table><tr><th>Symbol</th><th>Price</th></tr><tr><td>???</td><td>n/a</td></tr></table>"
    assert _scrape(html) == {}
    assert not s.LAST_STATUS["kenyanstocks.com"].startswith("ok")


def _cache(entries):
    return {t: {"price": 1.0, "source": src, "updated_at": (datetime.now() - timedelta(hours=h)).isoformat()}
            for t, (src, h) in entries.items()}


def test_cache_freshness_ignores_dict_order(monkeypatch):
    # Old entry first, fresh bulk entry second: must be served from cache.
    cache = _cache({"OLD": ("afx.kwayisi.org", 50), "NEW": ("kenyanstocks.com", 1)})
    monkeypatch.setattr(s, "_load_cache", lambda p: cache)
    monkeypatch.setattr(s, "_scrape_kenyanstocks_bulk", lambda: (_ for _ in ()).throw(AssertionError("refetched")))
    assert s.get_all_prices() is cache


def test_stale_bulk_cache_triggers_refetch(monkeypatch):
    cache = _cache({"A": ("kenyanstocks.com", 9)})
    monkeypatch.setattr(s, "_load_cache", lambda p: cache)
    monkeypatch.setattr(s, "_save_cache", lambda p, d: None)
    monkeypatch.setattr(s, "_scrape_kenyanstocks_bulk", lambda: {"A": {"price": 5.0, "change_pct": None, "volume": None}})
    assert s.get_all_prices()["A"]["price"] == 5.0
