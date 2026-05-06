from pathlib import Path

from journal.client import parse_member_list

FIXTURES = Path(__file__).parent / "fixtures"


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
