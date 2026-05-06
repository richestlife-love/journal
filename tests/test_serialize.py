import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from journal.report import (
    FullReport,
    MemberReport,
    ModeStats,
    WindowReport,
)
from journal.serialize import to_payload, write_site

SGT = ZoneInfo("Asia/Singapore")


def sgt(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=SGT)


def _stats(count, status, last_ts=None, dropped=0):
    return ModeStats(count=count, status=status, last_submission=last_ts, dropped_rows=dropped)


def _wr(raw_count, raw_status, dedup_count, dedup_status):
    return WindowReport(
        raw=_stats(raw_count, raw_status, last_ts=sgt(2026, 5, 5, 12)),
        dedup=_stats(dedup_count, dedup_status, last_ts=sgt(2026, 5, 5, 12)),
    )


def _full_report():
    # refreshed_at is INSIDE current_window so day/threshold are well-defined.
    return FullReport(
        refreshed_at=sgt(2026, 5, 5, 14),
        current_window=(sgt(2026, 4, 29, 8), sgt(2026, 5, 6, 8)),
        previous_window=(sgt(2026, 4, 22, 8), sgt(2026, 4, 29, 8)),
        members=[
            MemberReport(
                name="Jet",
                fetch_failed=None,
                current=_wr(7, "done", 7, "done"),
                previous=_wr(8, "done", 7, "done"),
            ),
            MemberReport(
                name="Aillyn",
                fetch_failed="HTTPError: 502",
                current=None,
                previous=None,
            ),
        ],
    )


def test_to_payload_top_level_keys():
    p = to_payload(_full_report())
    assert set(p.keys()) == {"version", "refreshed_at", "windows", "members"}


def test_to_payload_windows_block():
    p = to_payload(_full_report())
    assert p["windows"]["current"]["start"].endswith("+08:00")
    assert p["windows"]["current"]["end"].endswith("+08:00")
    assert "day" in p["windows"]["current"]
    assert "threshold" in p["windows"]["current"]
    # Previous window is closed → no day/threshold.
    assert "day" not in p["windows"]["previous"]
    assert "threshold" not in p["windows"]["previous"]


def test_to_payload_member_with_data():
    p = to_payload(_full_report())
    jet = next(m for m in p["members"] if m["name"] == "Jet")
    assert jet["current"]["raw"]["count"] == 7
    assert jet["current"]["raw"]["status"] == "done"
    assert jet["current"]["raw"]["last_submission"].endswith("+08:00")
    assert jet["current"]["raw"]["dropped_rows"] == 0
    assert jet["current"]["dedup"]["count"] == 7
    assert "fetch_failed" not in jet


def test_to_payload_member_with_search_failure():
    p = to_payload(_full_report())
    aillyn = next(m for m in p["members"] if m["name"] == "Aillyn")
    assert aillyn["fetch_failed"] == "HTTPError: 502"
    assert aillyn["current"] is None
    assert aillyn["previous"] is None


def test_write_site_writes_data_json_and_copies_static(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text(
        '<!doctype html><html><body><script type="application/json" id="data">__DATA__</script></body></html>'
    )
    (static / "app.js").write_text("console.log('hi');")
    (static / "style.css").write_text("body { font-family: sans-serif; }")

    out = tmp_path / "site"
    payload = to_payload(_full_report())

    write_site(payload, static_dir=static, out_dir=out)

    assert (out / "data.json").exists()
    assert (out / "app.js").read_text() == "console.log('hi');"
    assert (out / "style.css").read_text() == "body { font-family: sans-serif; }"
    html = (out / "index.html").read_text()
    assert "__DATA__" not in html
    # Embedded JSON parses back to the payload.
    import re
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S)
    assert m is not None
    assert json.loads(m.group(1)) == payload


def test_write_site_wipes_existing_out_dir(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("__DATA__")
    (static / "app.js").write_text("a")
    (static / "style.css").write_text("c")

    out = tmp_path / "site"
    out.mkdir()
    (out / "stale.txt").write_text("old")

    write_site(to_payload(_full_report()), static_dir=static, out_dir=out)
    assert not (out / "stale.txt").exists()
