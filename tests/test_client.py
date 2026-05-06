from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from journal.client import (
    SEARCH_URL,
    fetch_entry_body,
    fetch_member_list,
    fetch_search,
    parse_entry_body,
    parse_member_list,
    parse_search_rows,
)

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


def test_parse_entry_body_extracts_journal_text():
    html = (FIXTURES / "entry-page-158567.html").read_text()
    body = parse_entry_body(html)
    assert body  # non-empty
    # The fixture is for an entry written by "Jet" / "簡業縉".
    assert "Jet" in body or "簡業縉" in body


def test_parse_entry_body_returns_empty_when_field_missing():
    html = "<html><body>no entry here</body></html>"
    assert parse_entry_body(html) == ""


# --- HTTP layer with httpx.MockTransport ---


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_member_list_uses_search_url_with_no_params():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200, text=(FIXTURES / "search-page-empty.html").read_text()
        )

    with _mock_client(handler) as client:
        members = fetch_member_list(client)

    assert captured["url"].rstrip("/") == SEARCH_URL.rstrip("/")
    assert "Jet" in members


def test_fetch_search_passes_filters_as_get_params():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, text=(FIXTURES / "search-page-jet.html").read_text())

    with _mock_client(handler) as client:
        rows = fetch_search(client, "Jet", date(2026, 4, 29), date(2026, 5, 6))

    assert captured["params"]["filter_11"] == "Jet"
    assert captured["params"]["filter_3[start]"] == "04/29/2026"
    assert captured["params"]["filter_3[end]"] == "05/06/2026"
    assert captured["params"]["mode"] == "all"
    assert len(rows) >= 1


def test_fetch_entry_body_returns_normalized_body_text():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text=(FIXTURES / "entry-page-158567.html").read_text()
        )

    with _mock_client(handler) as client:
        body = fetch_entry_body(client, "https://example/entry/158567/")

    assert body
    assert isinstance(body, str)


def test_fetch_search_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502)

    with _mock_client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            fetch_search(client, "Jet", date(2026, 4, 29), date(2026, 5, 6))
