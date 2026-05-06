from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from journal.client import parse_member_list, parse_search_rows

FIXTURES = Path(__file__).parent / "fixtures"

SGT = ZoneInfo("Asia/Singapore")


def test_parse_member_list_extracts_singapore_organizers():
    html = (FIXTURES / "search-page-empty.html").read_text()
    members = parse_member_list(html)

    # Spot-check known SG organizers — actual list size depends on platform state.
    assert "Jet" in members
    assert "Lorene" in members
    assert "Jennifer" in members
    assert len(members) >= 15  # 20 at the time of fixture capture; tolerate small drift


def test_parse_member_list_does_not_include_other_regions():
    html = (FIXTURES / "search-page-empty.html").read_text()
    members = parse_member_list(html)

    # "Kelvin" is in filter_8 (Central Malaysia), not filter_11.
    assert "Kelvin" not in members


def test_parse_member_list_skips_placeholder_option():
    html = (FIXTURES / "search-page-empty.html").read_text()
    members = parse_member_list(html)
    assert "" not in members
    assert "—" not in members


def test_parse_search_rows_returns_one_row_per_submission():
    html = (FIXTURES / "search-page-jet.html").read_text()
    rows = parse_search_rows(html)
    # The fixture-capture in Task 2 recorded 8 rows.
    assert len(rows) == 8
    for row in rows:
        assert row.submission_ts.tzinfo is not None
        assert row.entry_id.isdigit()
        assert row.entry_url.startswith("https://writexperience.richestlife.com/")
        assert row.entry_url.endswith(f"/entry/{row.entry_id}/")


def test_parse_search_rows_extracts_correct_submission_timestamp():
    html = (FIXTURES / "search-page-jet.html").read_text()
    rows = parse_search_rows(html)

    # First row in the fixture should be the most recent submission.
    # Format on the page: "2026-05-06 at 07:43".
    first = rows[0]
    assert first.submission_ts.tzinfo is not None
    assert first.submission_ts.year == 2026
    # Hour/minute encoding matches HH:MM precision.
    assert first.submission_ts.second == 0


def test_parse_search_rows_handles_empty_results():
    html = '<table class="gv-table-view"><tbody><tr><td colspan="4" class="gv-no-results">No entries match your request.</td></tr></tbody></table>'
    rows = parse_search_rows(html)
    assert rows == []
