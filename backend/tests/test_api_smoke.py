"""
test_api_smoke.py — endpoint-level regression suite.

Run with: pytest tests/test_api_smoke.py -v

This is the actual safety net for a system used with real capital:
every route the frontend depends on gets a basic "does it return 200
and not corrupt state" check. Run this after ANY backend change,
before deploying, not just when something looks broken.

Deliberately does NOT test live external network calls (FRED/World
Bank/stooq) — those need real network access this suite can't assume.
See test_layers_1_4_mocked.py for that logic tested against mocked
responses, and README.md for the live-network verification checklist.
"""

import os
import sys
import shutil
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    import app
    return TestClient(app.app)


@pytest.fixture(autouse=True)
def _protect_real_data():
    """Snapshot portfolio_trades.csv before each test and restore it
    after — the test suite must never leave the user's real trade
    data in a different state than it found it."""
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    trades_path = os.path.join(data_dir, "portfolio_trades.csv")
    backup = None
    if os.path.exists(trades_path):
        with open(trades_path) as f:
            backup = f.read()
    yield
    if backup is not None:
        with open(trades_path, "w") as f:
            f.write(backup)
    # Clean up any recommendations_log.csv created by log-endpoint tests
    rec_log = os.path.join(data_dir, "recommendations_log.csv")
    if os.path.exists(rec_log):
        os.remove(rec_log)


GET_ENDPOINTS = [
    "/api/ping",
    "/api/system-status",
    "/api/tickers",
    "/api/sectors",
    "/api/stocks",
    "/api/portfolio",
    "/api/portfolio/risk",
    "/api/watchlist",
    "/api/data-health",
    "/api/stock/EQTY",
    "/api/stock/EQTY/recommendation",
    "/api/intelligence/global",
    "/api/intelligence/country",
    "/api/intelligence/sector",
    "/api/recommendations/history",
    "/api/recommendations/accuracy",
    "/api/recommendations/effectiveness",
    "/api/analytics",
]


@pytest.mark.parametrize("path", GET_ENDPOINTS)
def test_get_endpoint_returns_200(client, path):
    r = client.get(path)
    assert r.status_code == 200, f"{path} returned {r.status_code}: {r.text[:300]}"


def test_gold_endpoints_are_gone(client):
    """Gold trading module was deliberately removed — regression guard
    against it silently coming back via a merge or copy-paste."""
    for path in ["/api/gold/price", "/api/gold/candles", "/api/gold/signal"]:
        r = client.get(path)
        assert r.status_code == 404, f"{path} should be 404 (gold module removed) but got {r.status_code}"


def test_stock_detail_has_all_layers(client):
    """The stock detail endpoint must always include Layer 6/7/8
    output — regression guard against a field silently disappearing."""
    r = client.get("/api/stock/EQTY")
    assert r.status_code == 200
    d = r.json()
    for key in ["technical", "valuation", "capital_flow", "scores", "fundamentals"]:
        assert key in d, f"/api/stock/EQTY response missing '{key}' key"


def test_recommendation_reports_honest_coverage(client):
    """A recommendation must always state its coverage_pct — silently
    hiding degraded coverage would misrepresent confidence, which
    matters given this feeds real capital decisions."""
    r = client.get("/api/stock/EQTY/recommendation")
    assert r.status_code == 200
    d = r.json()
    if d.get("available"):
        assert "coverage_pct" in d
        assert "confidence" in d
        assert 0 <= d["coverage_pct"] <= 100


def test_portfolio_risk_has_diversification(client):
    r = client.get("/api/portfolio/risk")
    assert r.status_code == 200
    d = r.json()
    assert "sharpe_ratio" in d
    assert "diversification" in d
    assert "portfolio_health" in d


def test_concentrated_portfolio_cannot_be_labeled_excellent(client):
    """Regression guard for a real bug found via manual simulation:
    a 100%-concentrated single-holding portfolio was reporting
    'Excellent' health because Sharpe/drawdown look artificially
    perfect with too little history to mean anything — a dangerous
    label for a system used with real capital. The health score must
    never call a >=70%-concentrated position 'Excellent' or 'Good'."""
    from services.risk import portfolio_health_score
    sharpe = {"available": True, "value": 2.0}       # artificially "perfect"
    max_dd = {"available": True, "max_drawdown_pct": 0.0}  # artificially "perfect"
    diversification = {
        "available": True,
        "hhi_by_sector": 10000.0,
        "largest_position": {"ticker": "SOLO", "pct": 100.0},
    }
    health = portfolio_health_score(sharpe, max_dd, diversification)
    assert health["label"] not in ("Excellent", "Good"), (
        f"100%-concentrated portfolio must not be labeled '{health['label']}'"
    )
    assert health["concentration_capped"] is True


def test_year_is_not_hardcoded(client):
    """Regression guard for the hardcoded current_year=2024 bug that
    was found and fixed — this would silently mis-date charts every
    year if it ever came back."""
    import datetime
    r = client.get("/api/stock/EQTY")
    d = r.json()
    years = d.get("history_charts", {}).get("years") or []
    if years:
        assert max(years) <= datetime.datetime.now().year, (
            "history_charts years extend into the future — hardcoded year bug may have returned"
        )


def test_cors_is_not_wide_open_with_credentials(client):
    """Regression guard: allow_origins=['*'] + allow_credentials=True
    is both spec-invalid and an open security posture. Confirm the
    app never regresses to that combination."""
    import app as app_module
    origins = app_module._allowed_origins
    assert "*" not in origins, "CORS allow_origins must never be wildcard when allow_credentials=True"


def test_recommendation_log_and_history_roundtrip(client):
    """Layer 12: logging a recommendation must make it appear in history."""
    r = client.post("/api/recommendations/log", params={"ticker": "EQTY"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("success") is True
    rec_id = body["recommendation_id"]

    r2 = client.get("/api/recommendations/history")
    assert r2.status_code == 200
    ids = [h["recommendation_id"] for h in r2.json()["history"]]
    assert rec_id in ids


def test_unknown_ticker_returns_404_not_500(client):
    """A bad ticker should be a clean 404, not an unhandled crash."""
    r = client.get("/api/stock/ZZZNOTREAL/recommendation")
    assert r.status_code in (404, 400), f"Expected 404/400 for unknown ticker, got {r.status_code}"
