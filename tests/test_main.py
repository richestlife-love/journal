import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest.mock import patch

import httpx

from journal.__main__ import build

SGT = ZoneInfo("Asia/Singapore")
FIXTURES = Path(__file__).parent / "fixtures"


def test_build_end_to_end_with_mocked_http(tmp_path):
    """Run the full build with httpx MockTransport and verify outputs."""

    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text(
        '<!doctype html><html><body><script type="application/json" id="data">__DATA__</script></body></html>'
    )
    (static / "app.js").write_text("// app")
    (static / "style.css").write_text("/* css */")

    out = tmp_path / "site"
    cache_path = tmp_path / "cache.json"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/entry/" in url:
            return httpx.Response(200, text=(FIXTURES / "entry-page-158567.html").read_text())
        if "filter_11" in url:
            return httpx.Response(200, text=(FIXTURES / "search-page-jet.html").read_text())
        return httpx.Response(200, text=(FIXTURES / "search-page-empty.html").read_text())

    fixed_now = datetime(2026, 5, 6, 7, 0, tzinfo=SGT)
    with patch("journal.__main__._http_client", return_value=httpx.Client(transport=httpx.MockTransport(handler))), \
         patch("journal.__main__._now", return_value=fixed_now):
        rc = build(cache_path=cache_path, out_dir=out, static_dir=static)

    assert rc == 0
    payload = json.loads((out / "data.json").read_text())
    assert any(m["name"] == "Jet" for m in payload["members"])
    assert (out / "index.html").exists()
    assert (out / "app.js").read_text() == "// app"
    assert cache_path.exists()
