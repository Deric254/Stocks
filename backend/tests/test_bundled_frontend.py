"""The packaged executable must open to the UI at '/', not to the API banner.
(Bug: @app.get("/") returned JSON and, being registered first, shadowed the bundled frontend.)
Run in a subprocess because the decision is made at import time, as in the real exe."""
import json
import subprocess
import sys
import textwrap
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

SCRIPT = textwrap.dedent("""
    import json, sys
    sys.frozen = True            # behave like the PyInstaller exe: base path = sys._MEIPASS
    sys._MEIPASS = {bundle!r}
    import warnings; warnings.filterwarnings("ignore")
    import app
    from fastapi.testclient import TestClient
    c = TestClient(app.app)
    out = {{}}
    for p in ("/", "/dashboard", "/assets/app.js", "/api/ping", "/api/nope",
              "/..%2f..%2f..%2fsecret.txt", "/%2e%2e/secret.txt"):
        r = c.get(p)
        out[p] = [r.status_code, r.headers.get("content-type", ""), r.text[:60]]
    print("RESULT=" + json.dumps(out))
""")


def _run(bundle: Path, tmp_path: Path) -> dict:
    env = {"STOCKINTEL_DATA_DIR": str(tmp_path / "data"), "PATH": "/usr/bin:/bin"}
    cp = subprocess.run([sys.executable, "-c", SCRIPT.format(bundle=str(bundle))], cwd=BACKEND, env=env,
                        capture_output=True, text=True, timeout=120)
    line = next((l for l in cp.stdout.splitlines() if l.startswith("RESULT=")), None)
    assert line, cp.stdout + cp.stderr
    return json.loads(line[len("RESULT="):])


def test_packaged_app_serves_the_ui_at_root_and_keeps_the_api(tmp_path):
    bundle = tmp_path / "bundle"
    (bundle / "frontend" / "dist" / "assets").mkdir(parents=True)
    (bundle / "frontend" / "dist" / "index.html").write_text('<!doctype html><div id="root"></div>')
    (bundle / "frontend" / "dist" / "assets" / "app.js").write_text("console.log(1)")
    (bundle / "frontend" / "secret.txt").write_text("TOP SECRET")      # outside dist/, must stay unreachable
    (bundle / "VERSION").write_text("9.9.9")

    r = _run(bundle, tmp_path)
    assert r["/"][0] == 200 and 'id="root"' in r["/"][2], "root must serve the UI, not the API banner"
    assert 'id="root"' in r["/dashboard"][2], "client-side routes fall back to index.html"
    assert r["/assets/app.js"][2].startswith("console.log")
    assert r["/api/ping"][0] == 200 and "ok" in r["/api/ping"][2]
    assert r["/api/nope"][0] == 404 and "html" not in r["/api/nope"][1], "unknown API paths stay real 404s"
    for p in ("/..%2f..%2f..%2fsecret.txt", "/%2e%2e/secret.txt"):
        assert "TOP SECRET" not in r[p][2], "path traversal must not leak files outside dist/"


def test_without_bundled_ui_root_is_still_the_api_banner(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    r = _run(empty, tmp_path)
    assert r["/"][0] == 200 and "Stock Intel API" in r["/"][2], "the hosted API must behave exactly as before"
