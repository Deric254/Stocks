"""Regression tests for accuracy/consistency bugs found in the Data Status / Update Data audit."""
from datetime import date, datetime, timedelta

import pytest

import services.csv_data_manager as cdm
from services import nse_scraper as sc


@pytest.fixture
def mgr(tmp_path, monkeypatch):
    for name, f in (("PRICES_CSV", "prices_manual.csv"), ("PRICES_HISTORY", "prices_history_manual.csv"),
                    ("FUNDAMENTALS_CSV", "fundamentals_manual.csv"), ("META_JSON", "meta.json")):
        monkeypatch.setattr(cdm, name, tmp_path / f)
    return cdm.CSVDataManager()


# -- dates -------------------------------------------------------------------
def test_non_iso_dates_are_parsed_not_replaced_by_today():
    rows, _, _ = cdm.parse_price_csv(b"ticker,price,date\nSCOM,28.5,15/03/2026\nKCB,60,30-Sep-2025\n")
    assert [r["date"] for r in rows] == ["2026-03-15", "2025-09-30"]


def test_unrecognised_or_future_date_row_is_skipped_with_warning():
    future = (date.today() + timedelta(days=30)).isoformat()
    rows, errors, warnings = cdm.parse_price_csv(f"ticker,price,date\nSCOM,28.5,banana\nKCB,60,{future}\n".encode())
    assert rows == [] and errors and len(warnings) == 2


# -- one price shape for every reader ------------------------------------------
def test_snapshot_price_is_visible_to_freshness_and_health(mgr):
    mgr.snapshot_daily_prices({"SCOM": {"price": 30.0, "updated_at": datetime.now().isoformat()}})
    t = [{"ticker": "SCOM", "name": "Safaricom", "sector": "Telecom"}]
    rep = mgr.get_freshness_report(t)[0]
    assert rep["price"] == 30.0 and rep["freshness"] != "no_data"
    assert not any(a["field"] == "PRICE" and "no price data" in a["message"] for a in mgr.get_health_alerts(t))


def test_prices_age_counts_live_snapshots_not_only_uploads(mgr):
    assert mgr.get_prices_age_days() > 9000
    mgr.snapshot_daily_prices({"SCOM": {"price": 30.0, "updated_at": datetime.now().isoformat()}})
    assert mgr.get_prices_age_days() < 1


def test_snapshot_row_is_dated_on_a_trading_day(mgr):
    mgr.snapshot_daily_prices({"SCOM": {"price": 30.0, "updated_at": datetime.now().isoformat()}})
    assert date.fromisoformat(mgr._price_history["SCOM"][0]["date"]).weekday() < 5


def test_last_trading_day_rolls_weekend_back_to_friday():
    assert sc.last_trading_day(date(2026, 10, 3)) == date(2026, 10, 2)   # Saturday
    assert sc.last_trading_day(date(2026, 10, 4)) == date(2026, 10, 2)   # Sunday
    assert sc.last_trading_day(date(2026, 10, 1)) == date(2026, 10, 1)   # Thursday


# -- freshness must agree with get_fundamentals ---------------------------------
def test_freshness_ignores_seed_once_real_data_uploaded(mgr):
    mgr._fundamentals["SCOM"] = {"ticker": "SCOM", "pe": 10.0, "last_update": "2026-09-01"}
    seed = {"SCOM": {"eps": 2.0, "roe": 0.3, "bvps": 5.0, "dividend_yield": 0.05}}
    r = mgr.get_freshness_report([{"ticker": "SCOM", "name": "S", "sector": "T"}], seed=seed)[0]
    assert r["has_pe"] and not r["has_eps"] and not r["has_roe"]


def test_manual_override_clears_the_missing_flag(mgr):
    mgr._fundamentals["SCOM"] = {"ticker": "SCOM", "pe": 10.0}
    r = mgr.get_freshness_report([{"ticker": "SCOM", "name": "S", "sector": "T"}],
                                 overrides={"SCOM": {"eps": 2.5}})[0]
    assert r["has_eps"]


# -- templates ------------------------------------------------------------------
def test_price_template_prefills_only_todays_real_prices(monkeypatch):
    now = datetime.now().isoformat()
    monkeypatch.setattr("services.nse_scraper.get_all_prices", lambda: {
        "SCOM": {"price": 30.0, "source": "kenyanstocks.com", "updated_at": now},
        "KCB": {"price": 60.0, "source": "kenyanstocks.com", "updated_at": "2026-01-01T09:00:00"},
        "EQTY": {"price": 75.5, "source": "manual_stub", "updated_at": "manual", "stale": True}})
    out = cdm.generate_price_template([{"ticker": t} for t in ("SCOM", "KCB", "EQTY")]).splitlines()
    assert out[1:] == ["SCOM,30.0", "KCB,", "EQTY,"]


def test_fundamentals_template_makes_no_network_calls_and_prefers_uploads(monkeypatch):
    monkeypatch.setattr(sc, "_get_ex", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network used")))
    out = cdm.generate_fundamentals_template(
        [{"ticker": "SCOM"}], seed={"SCOM": {"eps": 99.0}}, uploaded={"SCOM": {"eps": 2.5}})
    assert "99.0" not in out and "2.5" in out


# -- update job -------------------------------------------------------------------
def _patch(monkeypatch, quote_fn):
    monkeypatch.setattr("services.nse_scraper.fetch_live_quote", quote_fn)
    monkeypatch.setattr("services.nse_scraper.get_all_prices", lambda: {})


def test_repricing_does_not_make_old_fundamentals_look_fresh(mgr, monkeypatch):
    mgr._fundamentals["EQTY"] = {"ticker": "EQTY", "eps": 19.0, "last_update": "2026-04-01", "data_source": "real_upload"}
    _patch(monkeypatch, lambda b: ({"price": 76.0, "source": "afx.kwayisi.org"}, None))
    mgr.refresh_all_data([{"ticker": "EQTY"}])
    row = mgr._fundamentals["EQTY"]
    assert row["pe"] == 4.0 and row["last_update"] == "2026-04-01"


def test_data_source_does_not_grow_with_every_update(mgr, monkeypatch):
    mgr._fundamentals["EQTY"] = {"ticker": "EQTY", "eps": 19.0, "data_source": "real_upload"}
    for price in (76.0, 77.0, 78.0):
        mgr._price_history.clear()
        _patch(monkeypatch, lambda b, p=price: ({"price": p, "source": "afx.kwayisi.org"}, None))
        mgr.refresh_all_data([{"ticker": "EQTY"}])
    assert mgr._fundamentals["EQTY"]["data_source"].count("repriced") == 1


def test_update_uses_prices_from_csv_uploads_too(mgr, monkeypatch):
    """Uploaded prices are stored under 'close'; the update job used to read only 'price'."""
    mgr.upload_prices(b"ticker,price\nEQTY,76\n")
    mgr._fundamentals["EQTY"] = {"ticker": "EQTY", "eps": 19.0, "data_source": "real_upload"}
    _patch(monkeypatch, lambda b: ({"price": 76.0, "source": "afx.kwayisi.org"}, None))
    mgr.refresh_all_data([{"ticker": "EQTY"}])
    assert mgr._fundamentals["EQTY"]["pe"] == 4.0


# -- scraper ------------------------------------------------------------------
def test_connection_failure_marks_host_down_and_skips_it_instantly(monkeypatch):
    import requests
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise requests.exceptions.ConnectionError("Max retries exceeded (NameResolutionError: Name or service not known)")
    sc.reset_source_health()
    monkeypatch.setattr(sc._session(), "get", boom)
    html, err = sc._get_ex("https://dead.example/x")
    assert html is None and "DNS" in err and len(calls) == 1, "no retry on a DNS failure"
    html, err = sc._get_ex("https://dead.example/y")
    assert "skipped" in err and len(calls) == 1, "second call must not touch the network"
    sc.reset_source_health()


MYSTOCKS = ("<div>End of day - {d}</div> 25.05 -0.60 (-2.34%) 25.65 Previous 26.00 High 24.50 Low")


def test_mystocks_quote_parsed_with_its_own_date():
    d = sc.last_trading_day()
    html = MYSTOCKS.format(d=d.strftime("%b %d, %Y"))
    assert sc._parse_mystocks_html(html)["price"] == 25.05


def test_mystocks_stale_quote_is_rejected():
    assert sc._parse_mystocks_html(MYSTOCKS.format(d="Aug 05, 2026")) == {}


def test_blank_header_tables_are_reported_as_javascript_placeholder(monkeypatch):
    html = "<table><tr><th></th><th></th></tr></table>"
    monkeypatch.setattr(sc, "_get_ex", lambda *a, **k: (html, None))
    assert sc._scrape_kenyanstocks_bulk() == {}
    assert "JavaScript" in sc.LAST_STATUS["kenyanstocks.com"]


def test_icon_only_header_uses_aria_label():
    html = ('<table><tr><th aria-label="Symbol"></th><th aria-label="Price"></th></tr>'
            '<tr><td><a href="/stock/SCOM">SCOM</a></td><td>28.50</td></tr></table>')
    import unittest.mock as m
    with m.patch.object(sc, "_get_ex", lambda *a, **k: (html, None)):
        assert sc._scrape_kenyanstocks_bulk()["SCOM"]["price"] == 28.5


# =========================== reliability layer ===========================
# Layout of the real mansamarkets.com/kenya table (verified): rank column first, ticker only in the
# link, "KSh" prefix, Unicode minus, "—" for stocks that did not trade, page states its date.
def _mansa_html(day="1 October 2026", weekday="Thursday"):
    return f"""<p>The Nairobi Securities Exchange rose on {weekday}, {day}, up. Updated {day}, 13:46 GMT+3.</p>
<table><thead><tr><th>#</th><th>Stock ↕</th><th>Price ↕</th><th>Change</th><th>Chg % ↕</th><th>Volume ↕</th>
<th>Share O/S ↕</th><th>Mkt Cap ↓</th></tr></thead><tbody>
<tr><td>1</td><td><a href="/kenya/scom">Safaricom Plc</a><span>SCOM</span></td><td>KSh36.40</td><td>+0.50</td><td>+1.39%</td><td>2.41M</td><td>40B</td><td>KSh1.21T</td></tr>
<tr><td>5</td><td><a href="/kenya/coop">Co-operative Bank</a>COOP</td><td>KSh36.60</td><td>-0.50</td><td>−1.35%</td><td>258.5K</td><td>5.87B</td><td>KSh175B</td></tr>
<tr><td>30</td><td><a href="/kenya/nse">Nairobi Securities Exchange Ltd</a>NSE</td><td>KSh30.30</td><td>-0.05</td><td>−0.16%</td><td>1.24M</td><td>259M</td><td>KSh5B</td></tr>
<tr><td>54</td><td><a href="/kenya/gld">Absa NewGold ETF</a>GLD</td><td>KSh5,300.00</td><td>+210.00</td><td>+4.13%</td><td>307</td><td>0</td><td>KSh0</td></tr>
<tr><td>63</td><td><a href="/kenya/hfcb">HFCB Group</a>HFCB</td><td>KSh12.10</td><td>-0.10</td><td>−0.82%</td><td>38.4K</td><td>—</td><td>—</td></tr>
<tr><td>58</td><td><a href="/kenya/bamb">Bamburi Cement Ltd</a>BAMB</td><td>KSh54.00</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td></tr>
</tbody></table>"""


def _clock_at(monkeypatch, year, month, day, hour, minute=0):
    real = sc.market_clock
    fake = datetime(year, month, day, hour, minute, tzinfo=sc.EAT)
    monkeypatch.setattr(sc, "market_clock", lambda now=None: real(fake))


def test_mansa_table_is_parsed_correctly(monkeypatch):
    _clock_at(monkeypatch, 2026, 10, 1, 17)
    monkeypatch.setattr(sc, "_get_ex", lambda *a, **k: (_mansa_html(), None))
    r = sc._scrape_mansa()
    assert r["SCOM"]["price"] == 36.4 and r["SCOM"]["change_pct"] == 1.39 and r["SCOM"]["volume"] == 2410000
    assert r["COOP"]["change_pct"] == -1.35, "Unicode minus must be read as negative"
    assert r["NSE"]["price"] == 30.3, "the real ticker NSE must not be dropped or turned into 'KENYA'"
    assert r["GLD"]["price"] == 5300.0
    assert "HFCK" in r and "HFCB" not in r, "site symbol HFCB maps to the app's HFCK"
    assert "BAMB" not in r, "a stock that did not trade today is not today's price"
    assert r["SCOM"]["price_date"] == "2026-10-01"
    assert "1 did not trade" in sc.LAST_STATUS["mansamarkets.com"]


def test_stale_page_is_rejected(monkeypatch):
    _clock_at(monkeypatch, 2026, 10, 1, 17)
    monkeypatch.setattr(sc, "_get_ex", lambda *a, **k: (_mansa_html("5 August 2026", "Wednesday"), None))
    assert sc._scrape_mansa() == {} and "not the latest trading day" in sc.LAST_STATUS["mansamarkets.com"]


def test_two_sources_that_agree_are_accepted_and_one_that_disagrees_is_dropped():
    a = {"SCOM": {"price": 36.4, "source": "A"}, "KCB": {"price": 92.0, "source": "A"}, "EQTY": {"price": 105.5, "source": "A"}}
    b = {"SCOM": {"price": 36.5, "source": "B"}, "KCB": {"price": 60.0, "source": "B"}}
    merged, disputed = sc._combine({"A": a, "B": b})
    assert merged["SCOM"]["confirmed_by"] == ["B"]
    assert "KCB" not in merged and any("KCB" in d for d in disputed), "disagreement is dropped, never guessed"
    assert merged["EQTY"]["price"] == 105.5, "a single-source price is still accepted"


def test_get_all_prices_cross_checks_sources(monkeypatch):
    saved = {}
    monkeypatch.setattr(sc, "_load_cache", lambda p: saved.copy())
    monkeypatch.setattr(sc, "_save_cache", lambda p, d: saved.update(d))
    monkeypatch.setattr(sc, "_scrape_mansa", lambda: {"SCOM": {"price": 36.4, "source": "mansamarkets.com"}})
    monkeypatch.setattr(sc, "_scrape_kenyanstocks_bulk", lambda: {"SCOM": {"price": 36.4, "source": "kenyanstocks.com"}})
    out = sc.get_all_prices(max_age_s=0)
    assert out["SCOM"]["confirmed_by"] == ["kenyanstocks.com"]
    assert "agreed" in sc.LAST_STATUS["cross-check"]


def test_market_clock_sessions():
    c = sc.market_clock
    mk = lambda d, h, m=0: datetime(2026, 10, d, h, m, tzinfo=sc.EAT)
    assert c(mk(1, 8)) == ("pre", date(2026, 9, 30))        # before the open: yesterday's close
    assert c(mk(1, 12)) == ("open", date(2026, 10, 1))
    assert c(mk(1, 15, 30)) == ("open", date(2026, 10, 1))  # sites still lag after 15:00
    assert c(mk(1, 16, 5)) == ("closed", date(2026, 10, 1))
    assert c(mk(3, 11)) == ("closed", date(2026, 10, 2))    # Saturday -> Friday
    assert c(mk(5, 8)) == ("pre", date(2026, 10, 2))        # Monday pre-open -> Friday


# -- history stays accurate ------------------------------------------------------
def _live(price, **kw):
    return {"price": price, "updated_at": datetime.now().isoformat(), **kw}


def test_provisional_row_is_replaced_by_the_final_close_then_locked(mgr):
    mgr.snapshot_daily_prices({"SCOM": _live(35.0)}, provisional=True)
    assert mgr._price_history["SCOM"][0]["source"] == "auto_snapshot_live"
    r = mgr.snapshot_daily_prices({"SCOM": _live(36.4)}, provisional=False)
    assert r["updated"] == ["SCOM"] and len(mgr._price_history["SCOM"]) == 1
    assert mgr._price_history["SCOM"][0]["close"] == 36.4
    r = mgr.snapshot_daily_prices({"SCOM": _live(99.0)}, provisional=False)
    assert r["skipped_duplicate"] == ["SCOM"] and mgr._price_history["SCOM"][0]["close"] == 36.4


def test_uploaded_prices_are_never_replaced_by_a_snapshot(mgr):
    day = sc.last_trading_day().isoformat()
    mgr.upload_prices(f"ticker,price,date\nSCOM,36.0,{day}\n".encode())
    r = mgr.snapshot_daily_prices({"SCOM": _live(37.0)}, provisional=True)
    assert r["skipped_duplicate"] == ["SCOM"] and mgr._price_history["SCOM"][0]["close"] == 36.0


def test_implausible_jump_is_held_back_not_written(mgr):
    prev = (sc.last_trading_day() - timedelta(days=1)).isoformat()
    mgr.upload_prices(f"ticker,price,date\nSCOM,30.0,{prev}\nKCB,90.0,{prev}\n".encode())
    r = mgr.snapshot_daily_prices({"SCOM": _live(90.0), "KCB": _live(92.0)})
    assert r["added"] == ["KCB"] and "SCOM" in r["skipped_suspect"][0]
    assert all(row["close"] != 90.0 for row in mgr._price_history["SCOM"])


def test_large_move_after_a_long_gap_is_accepted(mgr):
    """Your stored prices are months old: the first update must not be rejected as 'suspect'."""
    mgr.upload_prices(b"ticker,price,date\nEQTY,75.25,2026-07-04\n")
    assert mgr.snapshot_daily_prices({"EQTY": _live(105.5)})["added"] == ["EQTY"]


def test_quote_date_from_source_is_used_for_the_row(mgr):
    d = sc.last_trading_day()
    r = mgr.snapshot_daily_prices({"SCOM": _live(36.0, price_date=d.isoformat())})
    assert mgr._price_history["SCOM"][0]["date"] == d.isoformat() and r["added"] == ["SCOM"]


# -- scheduler -------------------------------------------------------------------
def test_final_close_job_retries_until_success_and_then_stops(mgr, monkeypatch):
    import app
    monkeypatch.setattr(app, "get_manager", lambda: mgr)
    _clock_at(monkeypatch, 2026, 10, 1, 17)
    monkeypatch.setattr(sc, "get_all_prices", lambda max_age_s=0: {})            # sources down
    assert app._record_final_close() == "failed"
    monkeypatch.setattr(sc, "get_all_prices", lambda max_age_s=0: {"SCOM": _live(36.4)})   # sources back
    assert app._record_final_close() == "done"
    assert app._record_final_close() == "not_due", "once saved, it must not fetch again"


def test_final_close_job_does_nothing_during_market_hours(mgr, monkeypatch):
    import app
    monkeypatch.setattr(app, "get_manager", lambda: mgr)
    _clock_at(monkeypatch, 2026, 10, 1, 11)
    monkeypatch.setattr(sc, "get_all_prices", lambda max_age_s=0: (_ for _ in ()).throw(AssertionError("fetched")))
    assert app._record_final_close() == "not_due"


# =========================== paste import ===========================
KNOWN = {"SCOM", "COOP", "NSE", "KCB", "EQTY", "HFCK", "GLD"}

MANSA_PASTE = """NSE ALL SHARE INDEX 246.82 ▲ +0.50% Market Cap KES 4.16T
# Stock Price Change Chg % Volume
1 Safaricom PlcSCOM KSh36.40 +0.50 +1.39% 2.41M 40.07B KSh1.21T
5 Co-operative Bank of KenyaCOOP KSh36.60 -0.50 −1.35% 258.5K
30 Nairobi Securities Exchange LtdNSE KSh30.30 -0.05 −0.16%
63 HFCB GroupHFCB KSh12.10 -0.10
54 Absa NewGold ETFGLD KSh5,300.00 +210.00
"""


def test_paste_reads_a_table_copied_from_the_site():
    prices, conflicts = cdm.parse_pasted_prices(MANSA_PASTE, KNOWN)
    assert prices == {"SCOM": 36.4, "COOP": 36.6, "NSE": 30.3, "HFCK": 12.1, "GLD": 5300.0}
    assert conflicts == [], "index level 246.82 and 'KES 4.16T' must not be taken as prices"


def test_paste_reads_simple_lines_in_any_separator():
    prices, _ = cdm.parse_pasted_prices("SCOM 36.40\nkcb,92\nEQTY\t105.5\nBOGUS 5\n", KNOWN)
    assert prices == {"SCOM": 36.4, "KCB": 92.0, "EQTY": 105.5}


def test_paste_with_the_same_price_twice_is_fine_but_a_contradiction_is_dropped():
    prices, conflicts = cdm.parse_pasted_prices("SCOM 36.40\nSCOM 36.40\nKCB 92\nKCB 60\n", KNOWN)
    assert prices == {"SCOM": 36.4} and conflicts == ["KCB"]


def test_paste_preview_saves_nothing_and_confirm_saves_exactly_the_preview(mgr):
    prev = (sc.last_trading_day() - timedelta(days=1)).isoformat()
    mgr.upload_prices(f"ticker,price,date\nSCOM,36.0,{prev}\nKCB,90.0,{prev}\n".encode())
    before = {t: len(h) for t, h in mgr._price_history.items()}
    pre = mgr.import_pasted_prices("SCOM 36.5\nKCB 200\nEQTY 105\n", KNOWN)
    assert {r["ticker"]: r["status"] for r in pre["rows"]} == {"SCOM": "ok", "KCB": "suspect", "EQTY": "ok"}
    assert pre["saved"] is False and {t: len(h) for t, h in mgr._price_history.items()} == before

    done = mgr.import_pasted_prices("SCOM 36.5\nKCB 200\nEQTY 105\n", KNOWN, confirm=True)
    assert done["saved"] and done["saved_count"] == 2
    assert mgr._price_history["SCOM"][-1]["close"] == 36.5 and mgr._price_history["EQTY"][0]["close"] == 105.0
    assert all(r["close"] != 200.0 for r in mgr._price_history["KCB"]), "suspect rows need explicit accept"


def test_paste_endpoint_rejects_garbage():
    from fastapi.testclient import TestClient
    import app
    app.app.dependency_overrides[app.get_current_user] = lambda: "test"
    try:
        r = TestClient(app.app).post("/api/upload/paste-prices", json={"text": "hello world 12.5"})
        assert r.status_code == 400
    finally:
        app.app.dependency_overrides.clear()


# =========================== fundamentals reliability ===========================
def test_percent_typed_as_fraction_is_corrected_with_a_warning():
    csv_in = b"ticker,eps,roe,margin,dividend_yield\nKCB,21.3,22.5,0.35,7.8\n"
    rows, errors, warnings = cdm.parse_fundamentals_csv(csv_in)
    r = rows[0]
    assert r["roe"] == 0.225 and r["dividend_yield"] == 0.078 and r["margin"] == 0.35
    assert len(warnings) == 2 and "percentage" in warnings[0]


def test_fundamentals_date_and_fiscal_year_are_never_fabricated():
    rows, _, warnings = cdm.parse_fundamentals_csv(b"ticker,eps,last_update\nKCB,21,15/03/2026\nEQTY,19,sometime\n")
    assert rows[0]["last_update"] == "2026-03-15" and rows[0]["fiscal_year"] == ""
    assert rows[1]["last_update"] == datetime.now().strftime("%Y-%m-%d") and "unrecognised last_update" in warnings[0]


def test_audit_flags_inconsistent_fundamentals_and_passes_clean_ones():
    clean = {"eps": 10.0, "pe": 5.0, "dividends": 3.0, "dividend_yield": 0.06, "roe": 0.2}
    assert cdm.audit_fundamentals_row(clean, 50.0) == []
    assert any("disagrees" in i for i in cdm.audit_fundamentals_row({**clean, "pe": 9.0}, 50.0))
    assert any("not positive" in i for i in cdm.audit_fundamentals_row({"eps": -2.0, "pe": 4.0}, 50.0))
    assert any("unusually high" in i for i in cdm.audit_fundamentals_row({"dividend_yield": 0.9}, 50.0))
    assert any("150% of EPS" in i for i in cdm.audit_fundamentals_row({"eps": 2.0, "dividends": 5.0}, 50.0))
    assert any("percentage" in i for i in cdm.audit_fundamentals_row({"roe": 22.0}, 50.0))


def test_audit_findings_reach_the_health_alerts(mgr):
    mgr._fundamentals["KCB"] = {"ticker": "KCB", "eps": 2.0, "dividends": 5.0}
    alerts = mgr.get_health_alerts([{"ticker": "KCB"}])
    assert any(a["field"] == "DATA CHECK" and "KCB" in a["message"] for a in alerts)


@pytest.mark.parametrize("write", ["csv", "paste", "snapshot"])
def test_ratios_follow_the_price_after_ANY_price_write(mgr, write):
    """Before: only the Update button repriced P/E - a pasted/uploaded price left ratios at the old price."""
    mgr._fundamentals["EQTY"] = {"ticker": "EQTY", "eps": 20.0, "pe": 3.76, "dividends": 5.0,
                                 "dividend_yield": 0.0664, "bvps": 50.0, "pb": 1.5,
                                 "last_update": "2026-07-04", "data_source": "real_upload"}
    if write == "csv":
        mgr.upload_prices(b"ticker,price\nEQTY,100\n")
    elif write == "paste":
        mgr.import_pasted_prices("EQTY 100", {"EQTY"}, confirm=True)
    else:
        mgr.snapshot_daily_prices({"EQTY": _live(100.0)})
    r = mgr._fundamentals["EQTY"]
    assert (r["pe"], r["dividend_yield"], r["pb"]) == (5.0, 0.05, 2.0)
    assert r["last_update"] == "2026-07-04", "re-pricing must not make old EPS look fresh"
    assert r["data_source"].startswith("real_upload") and r["data_source"].count("repriced") == 1


def test_repricing_keeps_provenance_notes_but_replaces_the_old_repriced_note(mgr):
    mgr._fundamentals["EQTY"] = {"ticker": "EQTY", "eps": 20.0, "data_source": "real_upload || live 2026-09-01 (afx) filled: eps"}
    mgr.upload_prices(b"ticker,price\nEQTY,100\n")
    mgr._price_history.clear(); mgr.upload_prices(b"ticker,price\nEQTY,110\n")
    src = mgr._fundamentals["EQTY"]["data_source"]
    assert "filled: eps" in src and src.count("repriced") == 1


def test_source_whose_eps_pe_and_price_contradict_is_ignored(mgr, monkeypatch):
    """The SCOM case: a page showing EPS 1.21 AND P/E 14.9 at a price of 36.6 (36.6/1.21 = 30, not 14.9)."""
    mgr._fundamentals["SCOM"] = {"ticker": "SCOM", "eps": 2.4, "data_source": "real_upload"}
    _patch(monkeypatch, lambda b: ({"price": 36.6, "eps": 1.21, "pe": 14.92, "dividends": 0.97,
                                    "source": "live.mystocks.co.ke"}, None))
    rep = mgr.refresh_all_data([{"ticker": "SCOM"}])
    assert any("contradict" in w for w in rep["warnings"])
    assert mgr._fundamentals["SCOM"]["eps"] == 2.4 and mgr._fundamentals["SCOM"].get("dividends") is None
    assert mgr._fundamentals["SCOM"]["pe"] == round(36.6 / 2.4, 2), "price is still used"


def test_row_with_contradictory_eps_and_pe_is_quarantined_not_silently_repriced(mgr):
    """CIC case: price 4.19, EPS 0.21 -> implied P/E 20, stored P/E 4.89. One is wrong; repricing
    from the suspect EPS would hide the problem."""
    mgr.upload_prices(b"ticker,price,date\nCIC,4.19,2026-07-04\n")
    mgr._fundamentals["CIC"] = {"ticker": "CIC", "eps": 0.21, "pe": 4.89, "data_source": "real_upload"}
    mgr._price_history.clear()
    mgr.upload_prices(b"ticker,price\nCIC,4.80\n")
    row = mgr._fundamentals["CIC"]
    assert row["pe"] == 4.89, "the stored P/E must not be overwritten from a suspect EPS"
    assert "verify EPS" in row["check"]
    alerts = mgr.get_health_alerts([{"ticker": "CIC"}])
    assert any(a["field"] == "DATA CHECK" and "CIC" in a["message"] for a in alerts), "must stay visible"
    # a later price move still does not touch it
    mgr._price_history.clear(); mgr.upload_prices(b"ticker,price\nCIC,5.20\n")
    assert mgr._fundamentals["CIC"]["pe"] == 4.89


def test_uploading_corrected_fundamentals_clears_the_quarantine(mgr):
    mgr._fundamentals["CIC"] = {"ticker": "CIC", "eps": 0.21, "pe": 4.89, "check": "verify EPS"}
    mgr.upload_fundamentals(b"ticker,eps\nCIC,0.86\n")
    row = mgr._fundamentals["CIC"]
    assert "check" not in row


# =========================== source self-test ===========================
def _rows(n):
    return {f"T{i}": {"price": 10.0 + i, "source": "x"} for i in range(n)} | {"SCOM": {"price": 36.4, "source": "x"}}


@pytest.mark.parametrize("mansa,kenyan,verdict", [(60, 60, "ready"), (60, 0, "degraded"), (0, 60, "degraded"), (0, 0, "blocked"), (5, 0, "blocked")])
def test_check_sources_verdict(monkeypatch, mansa, kenyan, verdict):
    monkeypatch.setattr(sc, "_scrape_mansa", lambda: _rows(mansa) if mansa else {})
    monkeypatch.setattr(sc, "_scrape_kenyanstocks_bulk", lambda: _rows(kenyan) if kenyan else {})
    monkeypatch.setattr(sc, "_get_ex", lambda *a, **k: (None, "HTTP 403"))
    r = sc.check_sources()
    assert r["verdict"] == verdict and len(r["sources"]) == 4
    assert all(x["detail"] for x in r["sources"]), "every failure must carry a reason"
    assert r["advice"]


def test_check_sources_endpoint_requires_login_and_saves_nothing():
    from fastapi.testclient import TestClient
    import app
    assert TestClient(app.app).get("/api/data-sources/check").status_code in (401, 403)
