import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from selectolax.parser import HTMLParser

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
