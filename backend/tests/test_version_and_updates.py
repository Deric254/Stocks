"""
test_version_and_updates.py — version reporting and the auto-update
check mechanism that other client systems poll.

Run with: pytest tests/test_version_and_updates.py -v
"""

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _fresh_app_client():
    """Reimport app fresh so module-level env-var reads (GITHUB_REPO)
    reflect whatever the test just set."""
    import importlib
    if "app" in sys.modules:
        importlib.reload(sys.modules["app"])
    else:
        import app  # noqa
    from fastapi.testclient import TestClient
    return TestClient(sys.modules["app"].app)


def test_version_endpoint_reads_real_version_file():
    client = _fresh_app_client()
    r = client.get("/api/version")
    assert r.status_code == 200
    body = r.json()
    assert "version" in body
    assert body["version"] != ""
    assert "frozen" in body


def test_update_check_without_github_repo_is_honest():
    """Must never silently claim 'no update available' when it simply
    isn't configured to check — that would be a false negative a
    client system could wrongly trust."""
    os.environ.pop("GITHUB_REPO", None)
    client = _fresh_app_client()
    r = client.get("/api/version/check")
    assert r.status_code == 200
    body = r.json()
    assert body["update_available"] is None, "must report unknown, not False, when unconfigured"


def test_update_check_detects_newer_version():
    os.environ["GITHUB_REPO"] = "exampleuser/stockintel"
    client = _fresh_app_client()

    mock_resp = mock.Mock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json = lambda: {
        "tag_name": "v9.9.9",
        "html_url": "https://github.com/exampleuser/stockintel/releases/tag/v9.9.9",
        "assets": [{"name": "app.exe", "browser_download_url": "https://example.com/app.exe", "size": 100}],
    }
    with mock.patch("requests.get", return_value=mock_resp):
        r = client.get("/api/version/check")
    body = r.json()
    assert body["update_available"] is True
    assert body["latest_version"] == "9.9.9"
    assert len(body["assets"]) == 1
    os.environ.pop("GITHUB_REPO", None)


def test_update_check_no_update_when_current():
    os.environ["GITHUB_REPO"] = "exampleuser/stockintel"
    client = _fresh_app_client()
    current = sys.modules["app"].APP_VERSION

    mock_resp = mock.Mock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json = lambda: {"tag_name": f"v{current}", "html_url": "x", "assets": []}
    with mock.patch("requests.get", return_value=mock_resp):
        r = client.get("/api/version/check")
    assert r.json()["update_available"] is False
    os.environ.pop("GITHUB_REPO", None)


def test_update_check_handles_github_unreachable_gracefully():
    os.environ["GITHUB_REPO"] = "exampleuser/stockintel"
    client = _fresh_app_client()
    with mock.patch("requests.get", side_effect=Exception("network unreachable")):
        r = client.get("/api/version/check")
    assert r.status_code == 200, "must not 500 just because GitHub is unreachable"
    assert r.json()["update_available"] is None
    os.environ.pop("GITHUB_REPO", None)
