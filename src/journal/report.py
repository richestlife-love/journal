from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Literal

from .cache import EntryCache
from .client import Row
from .dedup import body_hash, dedup_count, normalize_body
from .window import current_window, previous_window, threshold

Status = Literal["done", "on_track", "behind"]
TARGET = 7


@dataclass(frozen=True)
class ModeStats:
    count: int
    status: Status
    last_submission: datetime | None
    dropped_rows: int


@dataclass(frozen=True)
class WindowReport:
    raw: ModeStats
    dedup: ModeStats


@dataclass(frozen=True)
class MemberReport:
    name: str
    fetch_failed: str | None
    current: WindowReport | None
    previous: WindowReport | None

    @classmethod
    def from_search_failure(cls, name: str, error: str) -> "MemberReport":
        return cls(name=name, fetch_failed=error, current=None, previous=None)


def _status_current(count: int, threshold_: int) -> Status:
    if count >= TARGET:
        return "done"
    if count > threshold_:
        return "on_track"
    return "behind"


def _status_previous(count: int) -> Status:
    return "done" if count >= TARGET else "behind"


def _build_window_report(
    rows: list[Row],
    hashes_by_id: dict[str, str],
    dropped: int,
    is_current: bool,
    now: datetime,
    window: tuple[datetime, datetime],
) -> WindowReport:
    survivors = [r for r in rows if r.entry_id in hashes_by_id]
    raw_count = len(survivors)
    deduped_count = dedup_count([hashes_by_id[r.entry_id] for r in survivors])
    last_ts = max((r.submission_ts for r in survivors), default=None)

    if is_current:
        t = threshold(now, window)
        raw_status = _status_current(raw_count, t)
        dedup_status = _status_current(deduped_count, t)
    else:
        raw_status = _status_previous(raw_count)
        dedup_status = _status_previous(deduped_count)

    return WindowReport(
        raw=ModeStats(count=raw_count, status=raw_status, last_submission=last_ts, dropped_rows=dropped),
        dedup=ModeStats(count=deduped_count, status=dedup_status, last_submission=last_ts, dropped_rows=dropped),
    )


def build_member_report(
    name: str,
    rows: list[Row],
    now: datetime,
    *,
    cache: EntryCache,
    fetch_body: Callable[[str], str],
) -> MemberReport:
    """Build the per-member report from search rows + body fetches."""
    cur = current_window(now)
    prev = previous_window(now)

    in_cur = [r for r in rows if cur[0] <= r.submission_ts < cur[1]]
    in_prev = [r for r in rows if prev[0] <= r.submission_ts < prev[1]]

    hashes: dict[str, str] = {}
    dropped_cur = 0
    dropped_prev = 0

    for r in in_cur + in_prev:
        cached = cache.get(r.entry_id)
        if cached is not None:
            hashes[r.entry_id] = cached
            continue
        try:
            body = fetch_body(r.entry_url)
        except Exception:
            if r in in_cur:
                dropped_cur += 1
            if r in in_prev:
                dropped_prev += 1
            continue
        h = body_hash(normalize_body(body))
        cache.put(r.entry_id, h)
        hashes[r.entry_id] = h

    cur_report = _build_window_report(in_cur, hashes, dropped_cur, is_current=True, now=now, window=cur)
    prev_report = _build_window_report(in_prev, hashes, dropped_prev, is_current=False, now=now, window=prev)

    return MemberReport(name=name, fetch_failed=None, current=cur_report, previous=prev_report)
