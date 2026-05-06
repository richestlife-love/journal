from dataclasses import dataclass
from datetime import datetime

from selectolax.parser import HTMLParser


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
