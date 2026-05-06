from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

from journal.cache import EntryCache
from journal.client import Row
from journal.report import (
    FullReport,
    MemberReport,
    build_full_report,
    build_member_report,
)

SGT = ZoneInfo("Asia/Singapore")


def sgt(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=SGT)


def make_row(entry_id, ts):
    return Row(
        submission_ts=ts,
        entry_id=entry_id,
        entry_url=f"https://x/entry/{entry_id}/",
        preview="",
    )


def test_member_report_done_when_seven_distinct_in_current_window(tmp_path):
    cache = EntryCache.load(tmp_path / "c.json")
    rows = [
        make_row(str(i), sgt(2026, 4, 29 + (i // 24), 8 + (i % 24))) for i in range(7)
    ]
    bodies = {str(i): f"unique body {i}" for i in range(7)}

    def fetcher(url):
        return bodies[url.rsplit("/", 2)[-2]]

    now = sgt(2026, 5, 6, 7, 0)  # current window ends at Wed 8am
    rep = build_member_report("Jet", rows, now, cache=cache, fetch_body=fetcher)

    assert rep.fetch_failed is None
    assert rep.current.count == 7
    assert rep.current.status == "done"


def test_member_report_behind_when_below_threshold(tmp_path):
    cache = EntryCache.load(tmp_path / "c.json")
    # now = Day 5 (threshold 4); 3 distinct submissions → behind
    rows = [
        make_row("1", sgt(2026, 4, 29, 9, 0)),
        make_row("2", sgt(2026, 4, 30, 9, 0)),
        make_row("3", sgt(2026, 5, 1, 9, 0)),
    ]
    bodies = {"1": "a", "2": "b", "3": "c"}

    def fetcher(url):
        return bodies[url.rsplit("/", 2)[-2]]

    now = sgt(2026, 5, 3, 12, 0)  # Day 5

    rep = build_member_report("Jet", rows, now, cache=cache, fetch_body=fetcher)
    assert rep.current.count == 3
    assert rep.current.status == "behind"


def test_member_report_on_track_when_above_threshold(tmp_path):
    cache = EntryCache.load(tmp_path / "c.json")
    # now = Day 3 (threshold 2); 3 distinct submissions → on_track
    rows = [
        make_row("1", sgt(2026, 4, 29, 9, 0)),
        make_row("2", sgt(2026, 4, 30, 9, 0)),
        make_row("3", sgt(2026, 5, 1, 9, 0)),
    ]
    bodies = {"1": "a", "2": "b", "3": "c"}

    def fetcher(url):
        return bodies[url.rsplit("/", 2)[-2]]

    now = sgt(2026, 5, 1, 12, 0)  # Day 3

    rep = build_member_report("Jet", rows, now, cache=cache, fetch_body=fetcher)
    assert rep.current.count == 3
    assert rep.current.status == "on_track"


def test_member_report_dedup_collapses_identical_bodies(tmp_path):
    cache = EntryCache.load(tmp_path / "c.json")
    rows = [
        make_row("1", sgt(2026, 4, 29, 9, 0)),
        make_row("2", sgt(2026, 4, 30, 9, 0)),
        make_row("3", sgt(2026, 5, 1, 9, 0)),
    ]
    # Two of the three share content.
    bodies = {"1": "duplicate", "2": "duplicate", "3": "unique"}

    def fetcher(url):
        return bodies[url.rsplit("/", 2)[-2]]

    now = sgt(2026, 5, 5, 12, 0)

    rep = build_member_report("Jet", rows, now, cache=cache, fetch_body=fetcher)
    assert rep.current.count == 2


def test_member_report_uses_cache_and_skips_fetch_for_known_entries(tmp_path):
    cache = EntryCache.load(tmp_path / "c.json")
    cache.put("1", "sha256:cached")

    fetched_ids = []

    def fetcher(url):
        eid = url.rsplit("/", 2)[-2]
        fetched_ids.append(eid)
        return f"body of {eid}"

    rows = [
        make_row("1", sgt(2026, 4, 29, 9, 0)),
        make_row("2", sgt(2026, 4, 30, 9, 0)),
    ]
    now = sgt(2026, 5, 5, 12, 0)
    build_member_report("Jet", rows, now, cache=cache, fetch_body=fetcher)

    assert fetched_ids == ["2"]  # "1" was cached
    assert cache.get("2") is not None  # "2" got persisted into cache


def test_member_report_partial_entry_fetch_failure_drops_row(tmp_path):
    cache = EntryCache.load(tmp_path / "c.json")

    def fetcher(url):
        eid = url.rsplit("/", 2)[-2]
        if eid == "2":
            raise httpx.HTTPError("boom")
        return f"body of {eid}"

    rows = [
        make_row("1", sgt(2026, 4, 29, 9, 0)),
        make_row("2", sgt(2026, 4, 30, 9, 0)),
        make_row("3", sgt(2026, 5, 1, 9, 0)),
    ]
    now = sgt(2026, 5, 5, 12, 0)
    rep = build_member_report("Jet", rows, now, cache=cache, fetch_body=fetcher)

    assert rep.fetch_failed is None
    assert rep.current.dropped_rows == 1
    assert rep.current.count == 2  # 2 surviving distinct rows
    assert cache.get("2") is None  # failed entry NOT cached


def test_member_report_assigns_rows_to_correct_window(tmp_path):
    cache = EntryCache.load(tmp_path / "c.json")
    # now = 2026-05-06 09:00 → current = [05/06 08:00 .. 05/13 08:00),
    #                            previous = [04/29 08:00 .. 05/06 08:00)
    rows = [
        make_row("p1", sgt(2026, 5, 1, 9, 0)),  # previous window
        make_row("p2", sgt(2026, 5, 5, 9, 0)),  # previous window
        make_row("c1", sgt(2026, 5, 6, 9, 0)),  # current window
        make_row("oo", sgt(2026, 4, 28, 9, 0)),  # out of scope
    ]
    bodies = {"p1": "a", "p2": "b", "c1": "c", "oo": "d"}

    def fetcher(url):
        return bodies[url.rsplit("/", 2)[-2]]

    now = sgt(2026, 5, 6, 9, 0)

    rep = build_member_report("Jet", rows, now, cache=cache, fetch_body=fetcher)
    assert rep.previous.count == 2
    assert rep.current.count == 1


def test_member_report_search_failure_marks_member(tmp_path):
    rep = MemberReport.from_search_failure("Jet", "HTTPError: 502 Bad Gateway")
    assert rep.fetch_failed == "HTTPError: 502 Bad Gateway"
    assert rep.current is None
    assert rep.previous is None


def test_member_report_last_submission_uses_latest_row_even_when_deduped(tmp_path):
    cache = EntryCache.load(tmp_path / "c.json")
    rows = [
        make_row("1", sgt(2026, 5, 5, 9, 0)),
        make_row("2", sgt(2026, 5, 5, 18, 0)),
        make_row("3", sgt(2026, 5, 5, 14, 0)),
    ]
    bodies = {"1": "a", "2": "a", "3": "a"}  # all duplicates

    def fetcher(url):
        return bodies[url.rsplit("/", 2)[-2]]

    now = sgt(2026, 5, 6, 7, 0)

    rep = build_member_report("Jet", rows, now, cache=cache, fetch_body=fetcher)
    # Latest underlying row timestamp wins, even though dedup count is 1.
    assert rep.current.count == 1
    assert rep.current.last_submission == sgt(2026, 5, 5, 18, 0)


def test_previous_window_status_only_done_or_behind(tmp_path):
    cache = EntryCache.load(tmp_path / "c.json")
    rows = [make_row(str(i), sgt(2026, 4, 30, 9 + i, 0)) for i in range(3)]
    bodies = {str(i): f"u{i}" for i in range(3)}

    def fetcher(url):
        return bodies[url.rsplit("/", 2)[-2]]

    now = sgt(2026, 5, 6, 9, 0)  # previous window already closed

    rep = build_member_report("Jet", rows, now, cache=cache, fetch_body=fetcher)
    assert rep.previous.status in ("done", "behind")
    assert rep.previous.status == "behind"  # 3 < 7


def test_full_report_aggregates_all_members(tmp_path):
    cache = EntryCache.load(tmp_path / "c.json")
    now = sgt(2026, 5, 5, 12, 0)

    members = ["A", "B"]
    rows_by_member = {
        "A": [make_row("a1", sgt(2026, 5, 1, 9, 0))],
        "B": [make_row("b1", sgt(2026, 5, 1, 9, 0))],
    }
    bodies = {"a1": "x", "b1": "y"}

    def fetch_search(member, start, end):
        return rows_by_member[member]

    def fetch_body(url):
        return bodies[url.rsplit("/", 2)[-2]]

    rep = build_full_report(
        members=members,
        now=now,
        cache=cache,
        fetch_search=fetch_search,
        fetch_body=fetch_body,
    )

    assert isinstance(rep, FullReport)
    assert rep.refreshed_at == now
    assert {m.name for m in rep.members} == {"A", "B"}


def test_full_report_member_search_failure_does_not_kill_run(tmp_path):
    cache = EntryCache.load(tmp_path / "c.json")
    now = sgt(2026, 5, 5, 12, 0)

    def fetch_search(member, start, end):
        if member == "B":
            raise httpx.HTTPError("502")
        return [make_row("a1", sgt(2026, 5, 1, 9, 0))]

    def fetch_body(url):
        return "body"

    rep = build_full_report(
        members=["A", "B"],
        now=now,
        cache=cache,
        fetch_search=fetch_search,
        fetch_body=fetch_body,
    )
    by_name = {m.name: m for m in rep.members}
    assert by_name["A"].fetch_failed is None
    assert by_name["B"].fetch_failed is not None
    assert "502" in by_name["B"].fetch_failed


def test_full_report_uses_combined_date_range_for_search(tmp_path):
    cache = EntryCache.load(tmp_path / "c.json")
    now = sgt(2026, 5, 5, 12, 0)

    captured = {}

    def fetch_search(member, start, end):
        captured["start"] = start
        captured["end"] = end
        return []

    def fetch_body(url):
        return ""

    build_full_report(
        members=["A"],
        now=now,
        cache=cache,
        fetch_search=fetch_search,
        fetch_body=fetch_body,
    )

    # Range must cover both windows: previous starts on 2026-04-22 (Wed),
    # current ends on 2026-05-05 (day before current window boundary at 08:00 on May 6).
    assert captured["start"] == date(2026, 4, 22)
    assert captured["end"] == date(2026, 5, 5)
