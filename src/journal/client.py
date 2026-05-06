import re
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
from selectolax.parser import HTMLParser

from .dedup import normalize_body

_SGT = ZoneInfo("Asia/Singapore")
_TS_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})\s+at\s+(\d{2}):(\d{2})")
_ENTRY_ID_RE = re.compile(r"/entry/(\d+)/")


@dataclass(frozen=True)
class Row:
    submission_ts: datetime  # SGT-aware
    entry_id: str
    entry_url: str
    preview: str


def parse_member_list(html: str) -> list[str]:
    """Extract organizer names from <select name="filter_11"> options.

    Skips the placeholder option (empty value).
    """
    tree = HTMLParser(html)
    select = tree.css_first('select[name="filter_11"]')
    if select is None:
        return []
    members: list[str] = []
    for opt in select.css("option"):
        value = (opt.attributes.get("value") or "").strip()
        if value:
            members.append(value)
    return members


def parse_search_rows(html: str) -> list[Row]:
    """Parse the GravityView results table into Row records.

    Columns expected (by class):
        gv-field-7-custom (時間)            — submission timestamp text
        gv-field-7-3      (date link)       — link to entry, link text = submission date
        gv-field-7-custom (主持人)          — organizer (ignored here; filter already pinned it)
        gv-field-7-15     (心得)            — truncated journal preview
    """
    tree = HTMLParser(html)
    rows: list[Row] = []
    for tr in tree.css("tr[data-row]"):
        # Skip "no results" rows.
        if tr.css_first("td.gv-no-results") is not None:
            continue

        ts_cell = tr.css_first("td.gv-field-7-custom")
        link_cell = tr.css_first("td.gv-field-7-3 a")
        preview_cell = tr.css_first("td.gv-field-7-15")
        if ts_cell is None or link_cell is None:
            continue

        ts_match = _TS_RE.search(ts_cell.text())
        if ts_match is None:
            continue
        y, mo, d, h, mi = (int(x) for x in ts_match.groups())
        submission_ts = datetime(y, mo, d, h, mi, tzinfo=_SGT)

        href = link_cell.attributes.get("href") or ""
        id_match = _ENTRY_ID_RE.search(href)
        if id_match is None:
            continue
        entry_id = id_match.group(1)

        preview = preview_cell.text(separator=" ").strip() if preview_cell else ""

        rows.append(Row(
            submission_ts=submission_ts,
            entry_id=entry_id,
            entry_url=href,
            preview=preview,
        ))
    return rows


SEARCH_URL = "https://writexperience.richestlife.com/sg-check-experience/"


def parse_entry_body(html: str) -> str:
    """Extract and normalize the journal body from an entry detail page.

    Selector: `.gv-field-7-15` is the "心得" body field rendered in the entry view.
    Returns the empty string if absent.
    """
    tree = HTMLParser(html)
    field = tree.css_first(".gv-field-7-15")
    if field is None:
        return ""
    return normalize_body(field.html or "")


def fetch_member_list(client: httpx.Client) -> list[str]:
    """GET the search page and parse the SG member dropdown."""
    resp = client.get(SEARCH_URL)
    resp.raise_for_status()
    return parse_member_list(resp.text)


def fetch_search(
    client: httpx.Client,
    member: str,
    start: date,
    end: date,
) -> list[Row]:
    """GET the search results for a single member and date range."""
    params = {
        "filter_3[start]": start.strftime("%m/%d/%Y"),
        "filter_3[end]":   end.strftime("%m/%d/%Y"),
        "filter_11":       member,
        "mode":            "all",
    }
    resp = client.get(SEARCH_URL, params=params)
    resp.raise_for_status()
    return parse_search_rows(resp.text)


def fetch_entry_body(client: httpx.Client, entry_url: str) -> str:
    """GET an entry page and return its normalized body text."""
    resp = client.get(entry_url)
    resp.raise_for_status()
    return parse_entry_body(resp.text)
