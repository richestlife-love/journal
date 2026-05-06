import json
import shutil
from datetime import datetime
from pathlib import Path

from journal.report import FullReport, MemberReport, WindowStats
from journal.window import day_number, threshold


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _window_stats(s: WindowStats | None) -> dict | None:
    if s is None:
        return None
    return {
        "count": s.count,
        "status": s.status,
        "last_submission": _iso(s.last_submission),
        "dropped_rows": s.dropped_rows,
    }


def _member(m: MemberReport) -> dict:
    base = {
        "name": m.name,
        "current": _window_stats(m.current),
        "previous": _window_stats(m.previous),
    }
    if m.fetch_failed is not None:
        base["fetch_failed"] = m.fetch_failed
    return base


def to_payload(report: FullReport) -> dict:
    cur_start, cur_end = report.current_window
    prev_start, prev_end = report.previous_window

    return {
        "refreshed_at": report.refreshed_at.isoformat(),
        "windows": {
            "current": {
                "start": cur_start.isoformat(),
                "end": cur_end.isoformat(),
                "day": day_number(report.refreshed_at, report.current_window)
                if cur_start <= report.refreshed_at < cur_end
                else None,
                "threshold": threshold(report.refreshed_at, report.current_window),
            },
            "previous": {
                "start": prev_start.isoformat(),
                "end": prev_end.isoformat(),
            },
        },
        "members": [_member(m) for m in report.members],
    }


def write_site(payload: dict, *, static_dir: Path, out_dir: Path) -> None:
    """Wipe out_dir, write data.json, copy static assets, render index.html."""
    static_dir = Path(static_dir)
    out_dir = Path(out_dir)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    (out_dir / "data.json").write_text(json.dumps(payload, indent=2))

    for name in ("app.js", "style.css", "favicon.svg"):
        src = static_dir / name
        if src.exists():
            shutil.copy(src, out_dir / name)

    template = (static_dir / "index.html").read_text()
    rendered = template.replace("__DATA__", json.dumps(payload))
    (out_dir / "index.html").write_text(rendered)
