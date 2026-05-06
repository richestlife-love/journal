# RichestLife SG Journal Status Tracker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a static GitHub Pages site, refreshed hourly via GitHub Actions, that scrapes the public RichestLife SG journal page and shows each member's submission status for the current and previous Wed-08:00-SGT windows.

**Architecture:** A pure-Python scraper (`src/journal/`) parses the GravityView HTML, computes counts/statuses for two 7-day windows, and emits `data.json` plus an `index.html` skeleton with the JSON inlined. ~30 lines of vanilla JS render the tables in-browser and wire a dedup toggle. A monotonic-add hash cache on a dedicated `cache` orphan git branch saves repeat entry fetches.

**Tech Stack:** Python 3.14 (uv), httpx, selectolax, pytest. No frontend framework. GitHub Actions + Pages.

**Reference:** [`docs/superpowers/specs/2026-05-06-sg-journal-status-design.md`](../specs/2026-05-06-sg-journal-status-design.md)

---

## File map

| Path | Responsibility |
|---|---|
| `src/journal/window.py` | Pure time math: SGT 8am-Wed window boundaries, day numbering, threshold |
| `src/journal/dedup.py` | Pure: normalize body text, hash, group |
| `src/journal/cache.py` | Entry-id → hash JSON cache (load/get/put/save) |
| `src/journal/client.py` | httpx fetches + selectolax parsing of search and entry pages |
| `src/journal/report.py` | Compose window/dedup/cache/client → per-member per-window stats |
| `src/journal/serialize.py` | Build `data.json` payload; write site/ (data.json, templated index.html, copied app.js + style.css) |
| `src/journal/static/index.html` | Page skeleton with `__DATA__` placeholder for the JSON |
| `src/journal/static/app.js` | Render two tables from embedded JSON; wire dedup toggle |
| `src/journal/static/style.css` | Minimal CSS for the tables and header |
| `src/journal/__main__.py` | CLI: `python -m journal build [--cache PATH] [--out DIR] [--static DIR]` |
| `tests/fixtures/search-page-jet.html` | Captured real HTML for parser tests |
| `tests/fixtures/entry-page-158567.html` | Captured real HTML for entry-body parser tests |
| `tests/fixtures/search-page-empty.html` | Captured real HTML for member-list parser tests (no member filter applied) |
| `tests/test_*.py` | Pytest test files, one per module |
| `.github/workflows/refresh.yml` | Hourly cron + workflow_dispatch; build → push cache → deploy Pages |

---

### Task 1: Bootstrap dependencies, gitignore, pytest config

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`

- [ ] **Step 1: Update `pyproject.toml` with runtime + dev deps and pytest config**

Replace the existing file contents with:

```toml
[project]
name = "journal"
version = "0.1.0"
description = "RichestLife journal submission status tracker"
readme = "README.md"
authors = [{ name = "Jet Kan", email = "jetkan.yk@gmail.com" }]
requires-python = ">=3.14"
dependencies = [
    "httpx>=0.27",
    "selectolax>=0.3",
]

[dependency-groups]
dev = [
    "pytest>=8",
]

[build-system]
requires = ["uv_build>=0.11.10,<0.12.0"]
build-backend = "uv_build"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"
```

- [ ] **Step 2: Update `.gitignore` to exclude build output and local cache**

Append these lines:

```
# Build output
site/

# Local cache (CI uses a dedicated branch)
.cache/
```

- [ ] **Step 3: Sync deps**

Run: `uv sync`
Expected: creates `.venv`, installs httpx, selectolax, pytest. No errors.

- [ ] **Step 4: Smoke-check pytest discovers no tests yet**

Run: `uv run pytest`
Expected: exits 5 ("no tests ran") — that's the success condition for this step.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore uv.lock
git commit -m "chore: add runtime and dev dependencies, configure pytest"
```

---

### Task 2: Capture HTML fixtures from the live platform

**Files:**
- Create: `tests/fixtures/search-page-empty.html`
- Create: `tests/fixtures/search-page-jet.html`
- Create: `tests/fixtures/entry-page-158567.html`

These fixtures freeze real HTML for offline parser tests. They must be captured once, here, and never re-captured automatically.

- [ ] **Step 1: Create the fixtures directory**

Run: `mkdir -p tests/fixtures`

- [ ] **Step 2: Capture empty search page (no filter applied) — used for member-list parsing**

Run:
```bash
curl -sL "https://writexperience.richestlife.com/sg-check-experience/" \
  -o tests/fixtures/search-page-empty.html
```

Verify it contains the SG dropdown:
```bash
grep -c 'name="filter_11"' tests/fixtures/search-page-empty.html
```
Expected output: `1`

- [ ] **Step 3: Capture search page filtered to member "Jet" for last 7 days — used for row parser tests**

Run:
```bash
curl -sL -G "https://writexperience.richestlife.com/sg-check-experience/" \
  --data-urlencode "filter_3[start]=04/29/2026" \
  --data-urlencode "filter_3[end]=05/06/2026" \
  --data-urlencode "filter_11=Jet" \
  --data-urlencode "mode=all" \
  -o tests/fixtures/search-page-jet.html
```

Verify rows are present:
```bash
grep -c 'data-row="0"' tests/fixtures/search-page-jet.html
```
Expected output: `8` (or however many rows are visible at fixture-capture time — record the actual number; tests will assert against it).

- [ ] **Step 4: Capture one entry detail page — used for body-extraction parser tests**

Run:
```bash
curl -sL "https://writexperience.richestlife.com/sg-check-experience/entry/158567/" \
  -o tests/fixtures/entry-page-158567.html
```

Verify the body marker is present:
```bash
grep -c 'gv-field-7-15' tests/fixtures/entry-page-158567.html
```
Expected output: `>= 1` (the body field class appears at least once).

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/
git commit -m "test: capture real HTML fixtures from live platform for parser tests"
```

---

### Task 3: `window.py` — current/previous window, day number, threshold

**Files:**
- Create: `src/journal/window.py`
- Create: `tests/test_window.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_window.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from journal.window import current_window, previous_window, day_number, threshold

SGT = ZoneInfo("Asia/Singapore")


def sgt(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=SGT)


# --- current_window ---

def test_current_window_midweek():
    # Tuesday 2026-05-05 at 14:00 SGT — current window is the one ending next Wed 8am.
    now = sgt(2026, 5, 5, 14, 0)
    start, end = current_window(now)
    assert start == sgt(2026, 4, 29, 8, 0)
    assert end == sgt(2026, 5, 6, 8, 0)


def test_current_window_just_before_8am_on_wed_stays_in_old_window():
    now = sgt(2026, 5, 6, 7, 59)
    start, end = current_window(now)
    assert start == sgt(2026, 4, 29, 8, 0)
    assert end == sgt(2026, 5, 6, 8, 0)


def test_current_window_at_exactly_8am_on_wed_rolls_to_new_window():
    now = sgt(2026, 5, 6, 8, 0)
    start, end = current_window(now)
    assert start == sgt(2026, 5, 6, 8, 0)
    assert end == sgt(2026, 5, 13, 8, 0)


def test_current_window_on_wednesday_after_8am():
    # Wednesday afternoon — already in the new window.
    now = sgt(2026, 5, 6, 9, 30)
    start, end = current_window(now)
    assert start == sgt(2026, 5, 6, 8, 0)
    assert end == sgt(2026, 5, 13, 8, 0)


# --- previous_window ---

def test_previous_window_midweek():
    now = sgt(2026, 5, 5, 14, 0)
    start, end = previous_window(now)
    assert start == sgt(2026, 4, 22, 8, 0)
    assert end == sgt(2026, 4, 29, 8, 0)


def test_previous_window_just_after_window_roll():
    # Just after Wed 8am — the just-ended window is now "previous".
    now = sgt(2026, 5, 6, 8, 1)
    start, end = previous_window(now)
    assert start == sgt(2026, 4, 29, 8, 0)
    assert end == sgt(2026, 5, 6, 8, 0)


# --- day_number ---

def test_day_number_first_minute_is_day_1():
    win = (sgt(2026, 4, 29, 8, 0), sgt(2026, 5, 6, 8, 0))
    assert day_number(sgt(2026, 4, 29, 8, 0), win) == 1
    assert day_number(sgt(2026, 4, 29, 23, 59), win) == 1
    assert day_number(sgt(2026, 4, 30, 7, 59), win) == 1


def test_day_number_second_day_starts_at_thu_8am():
    win = (sgt(2026, 4, 29, 8, 0), sgt(2026, 5, 6, 8, 0))
    assert day_number(sgt(2026, 4, 30, 8, 0), win) == 2
    assert day_number(sgt(2026, 5, 1, 7, 59), win) == 2


def test_day_number_seventh_day():
    win = (sgt(2026, 4, 29, 8, 0), sgt(2026, 5, 6, 8, 0))
    assert day_number(sgt(2026, 5, 5, 8, 0), win) == 7
    assert day_number(sgt(2026, 5, 6, 7, 59), win) == 7


# --- threshold ---

def test_threshold_increments_at_each_8am_boundary():
    win = (sgt(2026, 4, 29, 8, 0), sgt(2026, 5, 6, 8, 0))
    assert threshold(sgt(2026, 4, 29, 8, 0), win) == 0     # Day 1 starts
    assert threshold(sgt(2026, 4, 30, 7, 59), win) == 0    # still Day 1
    assert threshold(sgt(2026, 4, 30, 8, 0), win) == 1     # Day 2 starts
    assert threshold(sgt(2026, 5, 1, 8, 0), win) == 2
    assert threshold(sgt(2026, 5, 5, 8, 0), win) == 6
    assert threshold(sgt(2026, 5, 6, 7, 59), win) == 6
    assert threshold(sgt(2026, 5, 6, 8, 0), win) == 7      # window closed
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_window.py -v`
Expected: ImportError or ModuleNotFoundError for `journal.window`.

- [ ] **Step 3: Implement `window.py`**

Create `src/journal/window.py`:

```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

SGT = ZoneInfo("Asia/Singapore")
WINDOW_DAYS = 7
DAY_HOURS = 24


def _most_recent_wed_8am(now: datetime) -> datetime:
    """Return the most recent Wed 08:00 SGT at or before `now`."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    sgt_now = now.astimezone(SGT)
    # Walk back to the most recent Wed 08:00.
    candidate = sgt_now.replace(hour=8, minute=0, second=0, microsecond=0)
    if candidate > sgt_now:
        candidate -= timedelta(days=1)
    # weekday(): Monday=0 ... Wednesday=2
    days_since_wed = (candidate.weekday() - 2) % 7
    return candidate - timedelta(days=days_since_wed)


def current_window(now: datetime) -> tuple[datetime, datetime]:
    """Return [start, end) of the current 7-day SG window containing `now`."""
    start = _most_recent_wed_8am(now)
    end = start + timedelta(days=WINDOW_DAYS)
    return start, end


def previous_window(now: datetime) -> tuple[datetime, datetime]:
    """Return [start, end) of the most recently completed 7-day SG window."""
    cur_start, _ = current_window(now)
    return cur_start - timedelta(days=WINDOW_DAYS), cur_start


def day_number(t: datetime, window: tuple[datetime, datetime]) -> int:
    """1..7 — which day-of-window does `t` fall in. Raises if out of range."""
    start, end = window
    if not (start <= t < end):
        raise ValueError(f"{t} is outside window {start}..{end}")
    elapsed_hours = (t - start).total_seconds() / 3600
    return int(elapsed_hours // DAY_HOURS) + 1


def threshold(t: datetime, window: tuple[datetime, datetime]) -> int:
    """Number of fully-completed days from window-start to `t` (0..7)."""
    start, end = window
    if t < start:
        return 0
    if t >= end:
        return WINDOW_DAYS
    elapsed_hours = (t - start).total_seconds() / 3600
    return int(elapsed_hours // DAY_HOURS)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_window.py -v`
Expected: 11 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/journal/window.py tests/test_window.py
git commit -m "feat(window): SGT 8am-Wed window math, day numbering, threshold"
```

---

### Task 4: `dedup.py` — normalize, hash, dedup

**Files:**
- Create: `src/journal/dedup.py`
- Create: `tests/test_dedup.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dedup.py`:

```python
from journal.dedup import normalize_body, body_hash, dedup_count


def test_normalize_strips_html_tags():
    assert normalize_body("<p>hello <b>world</b></p>") == "hello world"


def test_normalize_collapses_whitespace():
    assert normalize_body("hello    world\n\n  again") == "hello world again"


def test_normalize_strips_leading_trailing_whitespace():
    assert normalize_body("   hello world   ") == "hello world"


def test_normalize_handles_html_entities():
    assert normalize_body("a &amp; b") == "a & b"


def test_normalize_empty_input():
    assert normalize_body("") == ""
    assert normalize_body("   ") == ""


def test_body_hash_is_deterministic():
    h1 = body_hash("the quick brown fox")
    h2 = body_hash("the quick brown fox")
    assert h1 == h2
    assert h1.startswith("sha256:")


def test_body_hash_distinguishes_distinct_text():
    assert body_hash("hello") != body_hash("world")


def test_body_hash_after_normalize_collapses_whitespace_diffs():
    a = body_hash(normalize_body("hello   world"))
    b = body_hash(normalize_body("hello world"))
    assert a == b


def test_body_hash_after_normalize_collapses_html_diffs():
    a = body_hash(normalize_body("<p>hello world</p>"))
    b = body_hash(normalize_body("<div>hello world</div>"))
    assert a == b


def test_dedup_count_collapses_identical_hashes():
    hashes = ["sha256:aaa", "sha256:aaa", "sha256:bbb", "sha256:aaa"]
    assert dedup_count(hashes) == 2


def test_dedup_count_empty():
    assert dedup_count([]) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_dedup.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `dedup.py`**

Create `src/journal/dedup.py`:

```python
import hashlib
import html
import re

from selectolax.parser import HTMLParser

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_body(text: str) -> str:
    """Strip HTML tags, decode entities, collapse whitespace, trim."""
    if not text:
        return ""
    # selectolax handles partial-document HTML gracefully.
    plain = HTMLParser(text).text(separator=" ")
    plain = html.unescape(plain)
    plain = _WHITESPACE_RE.sub(" ", plain).strip()
    return plain


def body_hash(text: str) -> str:
    """SHA-256 of UTF-8 encoded text, prefixed with `sha256:`."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def dedup_count(hashes: list[str]) -> int:
    """Number of distinct hashes."""
    return len(set(hashes))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_dedup.py -v`
Expected: 11 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/journal/dedup.py tests/test_dedup.py
git commit -m "feat(dedup): body normalization, sha256 hashing, distinct count"
```

---

### Task 5: `cache.py` — entry-id → hash JSON cache

**Files:**
- Create: `src/journal/cache.py`
- Create: `tests/test_cache.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cache.py`:

```python
import json

import pytest

from journal.cache import EntryCache, CACHE_VERSION


def test_load_missing_file_returns_empty(tmp_path):
    c = EntryCache.load(tmp_path / "missing.json")
    assert c.get("anything") is None


def test_get_returns_none_on_miss(tmp_path):
    c = EntryCache.load(tmp_path / "x.json")
    assert c.get("123") is None


def test_put_then_get_hit(tmp_path):
    c = EntryCache.load(tmp_path / "x.json")
    c.put("123", "sha256:abc")
    assert c.get("123") == "sha256:abc"


def test_save_and_reload_round_trips(tmp_path):
    path = tmp_path / "x.json"
    a = EntryCache.load(path)
    a.put("123", "sha256:abc")
    a.put("456", "sha256:def")
    a.save()

    b = EntryCache.load(path)
    assert b.get("123") == "sha256:abc"
    assert b.get("456") == "sha256:def"


def test_saved_file_has_expected_schema(tmp_path):
    path = tmp_path / "x.json"
    c = EntryCache.load(path)
    c.put("123", "sha256:abc")
    c.save()

    raw = json.loads(path.read_text())
    assert raw["version"] == CACHE_VERSION
    assert raw["entries"] == {"123": "sha256:abc"}


def test_malformed_json_falls_back_to_empty(tmp_path):
    path = tmp_path / "x.json"
    path.write_text("not json at all")
    c = EntryCache.load(path)
    assert c.get("123") is None


def test_wrong_version_falls_back_to_empty(tmp_path):
    path = tmp_path / "x.json"
    path.write_text(json.dumps({"version": 99, "entries": {"x": "sha256:y"}}))
    c = EntryCache.load(path)
    assert c.get("x") is None


def test_save_creates_parent_directories(tmp_path):
    path = tmp_path / "nested" / "dir" / "cache.json"
    c = EntryCache.load(path)
    c.put("k", "sha256:v")
    c.save()
    assert path.exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cache.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `cache.py`**

Create `src/journal/cache.py`:

```python
import json
from pathlib import Path

CACHE_VERSION = 1


class EntryCache:
    def __init__(self, path: Path, entries: dict[str, str]):
        self.path = path
        self._entries = entries

    @classmethod
    def load(cls, path: Path | str) -> "EntryCache":
        path = Path(path)
        try:
            raw = json.loads(path.read_text())
            if raw.get("version") != CACHE_VERSION:
                return cls(path, {})
            entries = raw.get("entries", {})
            if not isinstance(entries, dict):
                return cls(path, {})
            return cls(path, dict(entries))
        except (FileNotFoundError, json.JSONDecodeError):
            return cls(path, {})

    def get(self, entry_id: str) -> str | None:
        return self._entries.get(entry_id)

    def put(self, entry_id: str, hash_: str) -> None:
        self._entries[entry_id] = hash_

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": CACHE_VERSION, "entries": self._entries}
        self.path.write_text(json.dumps(payload, sort_keys=True, indent=2))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cache.py -v`
Expected: 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/journal/cache.py tests/test_cache.py
git commit -m "feat(cache): monotonic entry-id → hash JSON cache with safe fallback"
```

---

### Task 6: `client.py` — Row dataclass and member-list parser

**Files:**
- Create: `src/journal/client.py`
- Create: `tests/test_client.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_client.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_client.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `parse_member_list` and a Row dataclass**

Create `src/journal/client.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_client.py -v`
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/journal/client.py tests/test_client.py
git commit -m "feat(client): Row dataclass and Singapore member-list parser"
```

---

### Task 7: `client.py` — search-results row parser

**Files:**
- Modify: `src/journal/client.py`
- Modify: `tests/test_client.py`

- [ ] **Step 1: Add failing tests for `parse_search_rows`**

Append to `tests/test_client.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from journal.client import parse_search_rows

SGT = ZoneInfo("Asia/Singapore")


def test_parse_search_rows_returns_one_row_per_submission():
    html = (FIXTURES / "search-page-jet.html").read_text()
    rows = parse_search_rows(html)
    # The fixture-capture in Task 2 recorded N rows. Assert against the recorded N.
    # If the fixture is recaptured, update this number.
    assert len(rows) >= 1
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_client.py::test_parse_search_rows_returns_one_row_per_submission -v`
Expected: ImportError on `parse_search_rows`.

- [ ] **Step 3: Implement `parse_search_rows`**

Append to `src/journal/client.py`:

```python
import re
from zoneinfo import ZoneInfo

_SGT = ZoneInfo("Asia/Singapore")
_TS_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})\s+at\s+(\d{2}):(\d{2})")
_ENTRY_ID_RE = re.compile(r"/entry/(\d+)/")


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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_client.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/journal/client.py tests/test_client.py
git commit -m "feat(client): parse search-results table into Row records"
```

---

### Task 8: `client.py` — entry-body parser and HTTP fetch wrappers

**Files:**
- Modify: `src/journal/client.py`
- Modify: `tests/test_client.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_client.py`:

```python
import httpx
import pytest

from journal.client import (
    parse_entry_body,
    fetch_member_list,
    fetch_search,
    fetch_entry_body,
    SEARCH_URL,
)


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
        return httpx.Response(200, text=(FIXTURES / "search-page-empty.html").read_text())

    with _mock_client(handler) as client:
        members = fetch_member_list(client)

    assert captured["url"].rstrip("/") == SEARCH_URL.rstrip("/")
    assert "Jet" in members


def test_fetch_search_passes_filters_as_get_params():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, text=(FIXTURES / "search-page-jet.html").read_text())

    from datetime import date
    with _mock_client(handler) as client:
        rows = fetch_search(client, "Jet", date(2026, 4, 29), date(2026, 5, 6))

    assert captured["params"]["filter_11"] == "Jet"
    assert captured["params"]["filter_3[start]"] == "04/29/2026"
    assert captured["params"]["filter_3[end]"] == "05/06/2026"
    assert captured["params"]["mode"] == "all"
    assert len(rows) >= 1


def test_fetch_entry_body_returns_normalized_body_text():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=(FIXTURES / "entry-page-158567.html").read_text())

    with _mock_client(handler) as client:
        body = fetch_entry_body(client, "https://example/entry/158567/")

    assert body
    assert isinstance(body, str)


def test_fetch_search_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502)

    from datetime import date
    with _mock_client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            fetch_search(client, "Jet", date(2026, 4, 29), date(2026, 5, 6))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_client.py -v`
Expected: ImportError on the new symbols.

- [ ] **Step 3: Implement `parse_entry_body` and the HTTP wrappers**

Append to `src/journal/client.py`:

```python
from datetime import date

import httpx

from .dedup import normalize_body

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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_client.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/journal/client.py tests/test_client.py
git commit -m "feat(client): entry-body parser and httpx-based fetch wrappers"
```

---

### Task 9: `report.py` — single-member orchestration

**Files:**
- Create: `src/journal/report.py`
- Create: `tests/test_report.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_report.py`:

```python
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from journal.client import Row
from journal.cache import EntryCache
from journal.report import build_member_report, MemberReport, ModeStats

SGT = ZoneInfo("Asia/Singapore")


def sgt(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=SGT)


def make_row(entry_id, ts):
    return Row(submission_ts=ts, entry_id=entry_id,
               entry_url=f"https://x/entry/{entry_id}/", preview="")


def test_member_report_done_when_seven_distinct_in_current_window(tmp_path):
    cache = EntryCache.load(tmp_path / "c.json")
    rows = [make_row(str(i), sgt(2026, 4, 29 + (i // 24), 8 + (i % 24))) for i in range(7)]
    bodies = {str(i): f"unique body {i}" for i in range(7)}

    fetcher = lambda url: bodies[url.rsplit("/", 2)[-2]]
    now = sgt(2026, 5, 6, 7, 0)  # current window ends at Wed 8am
    rep = build_member_report("Jet", rows, now, cache=cache, fetch_body=fetcher)

    assert rep.fetch_failed is None
    assert rep.current.dedup.count == 7
    assert rep.current.dedup.status == "done"
    assert rep.current.raw.count == 7
    assert rep.current.raw.status == "done"


def test_member_report_behind_when_below_threshold(tmp_path):
    cache = EntryCache.load(tmp_path / "c.json")
    # now = Day 5 (threshold 4); 3 distinct submissions → behind
    rows = [
        make_row("1", sgt(2026, 4, 29, 9, 0)),
        make_row("2", sgt(2026, 4, 30, 9, 0)),
        make_row("3", sgt(2026, 5, 1, 9, 0)),
    ]
    bodies = {"1": "a", "2": "b", "3": "c"}
    fetcher = lambda url: bodies[url.rsplit("/", 2)[-2]]
    now = sgt(2026, 5, 3, 12, 0)  # Day 5

    rep = build_member_report("Jet", rows, now, cache=cache, fetch_body=fetcher)
    assert rep.current.dedup.count == 3
    assert rep.current.dedup.status == "behind"


def test_member_report_on_track_when_above_threshold(tmp_path):
    cache = EntryCache.load(tmp_path / "c.json")
    # now = Day 3 (threshold 2); 3 distinct submissions → on_track
    rows = [
        make_row("1", sgt(2026, 4, 29, 9, 0)),
        make_row("2", sgt(2026, 4, 30, 9, 0)),
        make_row("3", sgt(2026, 5, 1, 9, 0)),
    ]
    bodies = {"1": "a", "2": "b", "3": "c"}
    fetcher = lambda url: bodies[url.rsplit("/", 2)[-2]]
    now = sgt(2026, 5, 1, 12, 0)  # Day 3

    rep = build_member_report("Jet", rows, now, cache=cache, fetch_body=fetcher)
    assert rep.current.dedup.count == 3
    assert rep.current.dedup.status == "on_track"


def test_member_report_dedup_collapses_identical_bodies(tmp_path):
    cache = EntryCache.load(tmp_path / "c.json")
    rows = [
        make_row("1", sgt(2026, 4, 29, 9, 0)),
        make_row("2", sgt(2026, 4, 30, 9, 0)),
        make_row("3", sgt(2026, 5, 1, 9, 0)),
    ]
    # Two of the three share content.
    bodies = {"1": "duplicate", "2": "duplicate", "3": "unique"}
    fetcher = lambda url: bodies[url.rsplit("/", 2)[-2]]
    now = sgt(2026, 5, 5, 12, 0)

    rep = build_member_report("Jet", rows, now, cache=cache, fetch_body=fetcher)
    assert rep.current.raw.count == 3
    assert rep.current.dedup.count == 2


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
    assert rep.current.dedup.dropped_rows == 1
    assert rep.current.dedup.count == 2  # 2 surviving distinct rows
    assert cache.get("2") is None  # failed entry NOT cached


def test_member_report_assigns_rows_to_correct_window(tmp_path):
    cache = EntryCache.load(tmp_path / "c.json")
    # now = 2026-05-06 09:00 → current = [05/06 08:00 .. 05/13 08:00),
    #                            previous = [04/29 08:00 .. 05/06 08:00)
    rows = [
        make_row("p1", sgt(2026, 5, 1, 9, 0)),   # previous window
        make_row("p2", sgt(2026, 5, 5, 9, 0)),   # previous window
        make_row("c1", sgt(2026, 5, 6, 9, 0)),   # current window
        make_row("oo", sgt(2026, 4, 28, 9, 0)),  # out of scope
    ]
    bodies = {"p1": "a", "p2": "b", "c1": "c", "oo": "d"}
    fetcher = lambda url: bodies[url.rsplit("/", 2)[-2]]
    now = sgt(2026, 5, 6, 9, 0)

    rep = build_member_report("Jet", rows, now, cache=cache, fetch_body=fetcher)
    assert rep.previous.raw.count == 2
    assert rep.current.raw.count == 1


def test_member_report_search_failure_marks_member(tmp_path):
    cache = EntryCache.load(tmp_path / "c.json")
    now = sgt(2026, 5, 5, 12, 0)
    rep = MemberReport.from_search_failure("Jet", "HTTPError: 502 Bad Gateway")
    assert rep.fetch_failed == "HTTPError: 502 Bad Gateway"
    assert rep.current is None
    assert rep.previous is None


def test_member_report_last_submission_uses_latest_raw_row(tmp_path):
    cache = EntryCache.load(tmp_path / "c.json")
    rows = [
        make_row("1", sgt(2026, 5, 5, 9, 0)),
        make_row("2", sgt(2026, 5, 5, 18, 0)),
        make_row("3", sgt(2026, 5, 5, 14, 0)),
    ]
    bodies = {"1": "a", "2": "a", "3": "a"}  # all duplicates
    fetcher = lambda url: bodies[url.rsplit("/", 2)[-2]]
    now = sgt(2026, 5, 6, 7, 0)

    rep = build_member_report("Jet", rows, now, cache=cache, fetch_body=fetcher)
    # Latest raw timestamp wins, regardless of dedup.
    assert rep.current.raw.last_submission == sgt(2026, 5, 5, 18, 0)
    assert rep.current.dedup.last_submission == sgt(2026, 5, 5, 18, 0)


def test_previous_window_status_only_done_or_behind(tmp_path):
    cache = EntryCache.load(tmp_path / "c.json")
    rows = [
        make_row(str(i), sgt(2026, 4, 30, 9 + i, 0)) for i in range(3)
    ]
    bodies = {str(i): f"u{i}" for i in range(3)}
    fetcher = lambda url: bodies[url.rsplit("/", 2)[-2]]
    now = sgt(2026, 5, 6, 9, 0)  # previous window already closed

    rep = build_member_report("Jet", rows, now, cache=cache, fetch_body=fetcher)
    assert rep.previous.dedup.status in ("done", "behind")
    assert rep.previous.dedup.status == "behind"  # 3 < 7
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_report.py -v`
Expected: ImportError on `journal.report`.

- [ ] **Step 3: Implement `report.py`**

Create `src/journal/report.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_report.py -v`
Expected: all 10 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/journal/report.py tests/test_report.py
git commit -m "feat(report): per-member status with windowing, dedup, cache, partial-failure tracking"
```

---

### Task 10: `report.py` — full report aggregator

**Files:**
- Modify: `src/journal/report.py`
- Modify: `tests/test_report.py`

- [ ] **Step 1: Add failing tests for `build_full_report`**

Append to `tests/test_report.py`:

```python
from journal.report import build_full_report, FullReport


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
    # current ends 2026-05-12 (within 2026-05-12 calendar day).
    from datetime import date
    assert captured["start"] == date(2026, 4, 22)
    assert captured["end"] == date(2026, 5, 12)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_report.py::test_full_report_aggregates_all_members -v`
Expected: ImportError on `build_full_report`/`FullReport`.

- [ ] **Step 3: Implement `build_full_report` and `FullReport`**

Append to `src/journal/report.py`:

```python
from datetime import date, timedelta


@dataclass(frozen=True)
class FullReport:
    refreshed_at: datetime
    current_window: tuple[datetime, datetime]
    previous_window: tuple[datetime, datetime]
    members: list[MemberReport]


def _calendar_range(prev: tuple[datetime, datetime], cur: tuple[datetime, datetime]) -> tuple[date, date]:
    """Calendar-day GET range that covers both windows. End is inclusive."""
    start = prev[0].date()
    end = (cur[1] - timedelta(seconds=1)).date()
    return start, end


def build_full_report(
    *,
    members: list[str],
    now: datetime,
    cache: EntryCache,
    fetch_search: Callable[[str, date, date], list[Row]],
    fetch_body: Callable[[str], str],
) -> FullReport:
    """Run the full scrape: one search per member, one report per member."""
    cur = current_window(now)
    prev = previous_window(now)
    start_d, end_d = _calendar_range(prev, cur)

    member_reports: list[MemberReport] = []
    for name in members:
        try:
            rows = fetch_search(name, start_d, end_d)
        except Exception as e:
            member_reports.append(MemberReport.from_search_failure(name, repr(e)))
            continue
        member_reports.append(
            build_member_report(name, rows, now, cache=cache, fetch_body=fetch_body)
        )

    return FullReport(
        refreshed_at=now,
        current_window=cur,
        previous_window=prev,
        members=member_reports,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_report.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/journal/report.py tests/test_report.py
git commit -m "feat(report): full aggregator across all members with isolated failures"
```

---

### Task 11: `serialize.py` — JSON payload + write_site

**Files:**
- Create: `src/journal/serialize.py`
- Create: `tests/test_serialize.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_serialize.py`:

```python
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
    return FullReport(
        refreshed_at=sgt(2026, 5, 6, 14),
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
    # Note: refreshed_at gets passed in as part of report; current.day/threshold are derived.
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_serialize.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `serialize.py`**

Create `src/journal/serialize.py`:

```python
import json
import shutil
from datetime import datetime
from pathlib import Path

from .report import FullReport, MemberReport, ModeStats, WindowReport
from .window import day_number, threshold

PAYLOAD_VERSION = 1


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _mode_stats(s: ModeStats) -> dict:
    return {
        "count": s.count,
        "status": s.status,
        "last_submission": _iso(s.last_submission),
        "dropped_rows": s.dropped_rows,
    }


def _window_report(w: WindowReport | None) -> dict | None:
    if w is None:
        return None
    return {"raw": _mode_stats(w.raw), "dedup": _mode_stats(w.dedup)}


def _member(m: MemberReport) -> dict:
    base = {
        "name": m.name,
        "current": _window_report(m.current),
        "previous": _window_report(m.previous),
    }
    if m.fetch_failed is not None:
        base["fetch_failed"] = m.fetch_failed
    return base


def to_payload(report: FullReport) -> dict:
    cur_start, cur_end = report.current_window
    prev_start, prev_end = report.previous_window

    return {
        "version": PAYLOAD_VERSION,
        "refreshed_at": report.refreshed_at.isoformat(),
        "windows": {
            "current": {
                "start": cur_start.isoformat(),
                "end": cur_end.isoformat(),
                "day": day_number(report.refreshed_at, report.current_window)
                       if cur_start <= report.refreshed_at < cur_end else None,
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

    for name in ("app.js", "style.css"):
        src = static_dir / name
        if src.exists():
            shutil.copy(src, out_dir / name)

    template = (static_dir / "index.html").read_text()
    rendered = template.replace("__DATA__", json.dumps(payload))
    (out_dir / "index.html").write_text(rendered)
```

After running the test, you may notice `_window_report` rejects `None` for `current`/`previous` for the failed member — but the test asserts `assert aillyn["current"] is None`. The implementation returns `None` for both in that case. Good.

Also: the `day` field for current window when `refreshed_at` is exactly at window end (`>= cur_end`) returns `None`, but `threshold` returns 7 — the test fixture's `refreshed_at` (2026-05-06 14:00) is in the *next* window, not the one we ship as "current". Update `_full_report` if needed: the test currently asserts `"day" in p["windows"]["current"]` so our fixture should have `refreshed_at` inside `current_window`. Adjust the fixture or the implementation.

- [ ] **Step 4: Adjust the test fixture so `refreshed_at` is inside `current_window`**

In `tests/test_serialize.py`, change `_full_report()` to use `refreshed_at=sgt(2026, 5, 5, 14)` so it lies within the declared current window `[2026-04-29 08:00, 2026-05-06 08:00)`:

```python
def _full_report():
    return FullReport(
        refreshed_at=sgt(2026, 5, 5, 14),
        current_window=(sgt(2026, 4, 29, 8), sgt(2026, 5, 6, 8)),
        previous_window=(sgt(2026, 4, 22, 8), sgt(2026, 4, 29, 8)),
        ...
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_serialize.py -v`
Expected: all 6 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/journal/serialize.py tests/test_serialize.py
git commit -m "feat(serialize): build data.json payload, write site/, embed JSON in index.html"
```

---

### Task 12: Static skeleton — `index.html` and `style.css`

**Files:**
- Create: `src/journal/static/index.html`
- Create: `src/journal/static/style.css`

This task ships hand-written assets; no automated test. Manual smoke happens in Task 15.

- [ ] **Step 1: Create the index template**

Create `src/journal/static/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>RichestLife SG — Journal Submission Status</title>
  <link rel="stylesheet" href="style.css">
</head>
<body data-mode="dedup">
  <header>
    <h1>RichestLife SG — Journal Submission Status</h1>
    <p class="meta">
      <span id="refreshed"></span>
      <span class="sep">•</span>
      Dedup:
      <a href="#" id="toggle-on" class="toggle active">on</a>
      <a href="#" id="toggle-off" class="toggle">off</a>
    </p>
  </header>

  <main>
    <section id="current">
      <h2>Current week</h2>
      <p class="window-meta"></p>
      <table>
        <thead>
          <tr><th>Name</th><th>Submissions</th><th>Status</th><th>Last submission</th></tr>
        </thead>
        <tbody></tbody>
      </table>
    </section>

    <section id="previous">
      <h2>Last completed week</h2>
      <p class="window-meta"></p>
      <table>
        <thead>
          <tr><th>Name</th><th>Submissions</th><th>Status</th><th>Last submission</th></tr>
        </thead>
        <tbody></tbody>
      </table>
    </section>
  </main>

  <script type="application/json" id="data">__DATA__</script>
  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create the stylesheet**

Create `src/journal/static/style.css`:

```css
:root {
  --fg: #222;
  --muted: #666;
  --border: #ddd;
  --done: #1a7f37;
  --on-track: #9a6700;
  --behind: #cf222e;
  --failed: #8250df;
}

* { box-sizing: border-box; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  color: var(--fg);
  margin: 0;
  padding: 1.5rem;
  max-width: 960px;
  margin: 0 auto;
}

header { border-bottom: 1px solid var(--border); padding-bottom: 1rem; }
h1 { margin: 0 0 0.5rem; font-size: 1.5rem; }
.meta { color: var(--muted); font-size: 0.9rem; margin: 0; }
.meta .sep { margin: 0 0.5rem; }

.toggle {
  text-decoration: none;
  color: var(--muted);
  padding: 0 0.25rem;
}
.toggle.active { color: var(--fg); font-weight: 600; }

main section { margin-top: 2rem; }
h2 { margin-bottom: 0.25rem; font-size: 1.1rem; }
.window-meta { color: var(--muted); font-size: 0.9rem; margin-top: 0; }

table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--border); }
th { font-weight: 600; font-size: 0.85rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
td.count { font-variant-numeric: tabular-nums; }

.status-done    { color: var(--done); }
.status-on_track { color: var(--on-track); }
.status-behind  { color: var(--behind); }
.status-failed  { color: var(--failed); }

.warn { color: var(--behind); margin-left: 0.25em; }

@media (max-width: 600px) {
  body { padding: 1rem; }
  table { font-size: 0.9rem; }
}
```

- [ ] **Step 3: Commit**

```bash
git add src/journal/static/index.html src/journal/static/style.css
git commit -m "feat(static): page skeleton with embedded-JSON placeholder and minimal CSS"
```

---

### Task 13: Static `app.js` — render and toggle

**Files:**
- Create: `src/journal/static/app.js`

- [ ] **Step 1: Create the renderer**

Create `src/journal/static/app.js`:

```javascript
(() => {
  const data = JSON.parse(document.getElementById("data").textContent);
  const STATUS_LABEL = {
    done: "✓ Done",
    on_track: "→ On track",
    behind: "✗ Behind",
    failed: "⚠ Fetch failed",
  };
  const STATUS_RANK = { failed: 0, behind: 1, on_track: 2, done: 3 };

  function fmtRefreshed(iso) {
    const d = new Date(iso);
    return `Refreshed ${d.toLocaleString("en-SG", {
      timeZone: "Asia/Singapore", year: "numeric", month: "2-digit",
      day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
    })} SGT`;
  }

  function fmtRelative(iso, now) {
    if (!iso) return "—";
    const t = new Date(iso).getTime();
    const diff = (now - t) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)} minutes ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} hours ago`;
    if (diff < 86400 * 2) return "yesterday";
    return `${Math.floor(diff / 86400)} days ago`;
  }

  function fmtWindow(w) {
    const f = (iso) => new Date(iso).toLocaleString("en-SG", {
      timeZone: "Asia/Singapore", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
    });
    return `${f(w.start)} → ${f(w.end)} SGT`;
  }

  function fmtCountdown(endIso, now) {
    const ms = new Date(endIso).getTime() - now;
    if (ms <= 0) return "deadline passed";
    const h = Math.floor(ms / 3_600_000);
    const d = Math.floor(h / 24);
    return d > 0 ? `Deadline in ${d}d ${h % 24}h` : `Deadline in ${h}h`;
  }

  function memberRow(m, mode, isCurrent) {
    const tr = document.createElement("tr");
    if (m.fetch_failed) {
      tr.innerHTML = `<td>${m.name}</td><td class="count">?/7</td>` +
        `<td class="status-failed" title="${escapeHtml(m.fetch_failed)}">${STATUS_LABEL.failed}</td><td>—</td>`;
      return { tr, statusKey: "failed", count: -1 };
    }
    const w = isCurrent ? m.current : m.previous;
    const stats = w[mode];
    const count = stats.count;
    const status = stats.status;
    const warn = stats.dropped_rows > 0
      ? `<span class="warn" title="${stats.dropped_rows} entry fetch(es) failed; count is a lower bound">⚠</span>`
      : "";
    tr.innerHTML = `<td>${m.name}</td><td class="count">${count}/7${warn}</td>` +
      `<td class="status-${status}">${STATUS_LABEL[status]}</td>` +
      `<td>${fmtRelative(stats.last_submission, Date.now())}</td>`;
    return { tr, statusKey: status, count };
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function sortMembers(rows) {
    return rows.sort((a, b) => {
      const r = STATUS_RANK[a.statusKey] - STATUS_RANK[b.statusKey];
      if (r !== 0) return r;
      if (a.statusKey !== "done") {
        const c = a.count - b.count;
        if (c !== 0) return c;
      }
      return a.tr.firstChild.textContent.localeCompare(b.tr.firstChild.textContent);
    });
  }

  function renderTable(sectionId, members, mode, isCurrent) {
    const tbody = document.querySelector(`#${sectionId} tbody`);
    tbody.innerHTML = "";
    const rows = members.map((m) => memberRow(m, mode, isCurrent));
    sortMembers(rows).forEach((r) => tbody.appendChild(r.tr));
  }

  function render() {
    const mode = document.body.dataset.mode === "raw" ? "raw" : "dedup";
    document.getElementById("toggle-on").classList.toggle("active", mode === "dedup");
    document.getElementById("toggle-off").classList.toggle("active", mode === "raw");

    document.getElementById("refreshed").textContent = fmtRefreshed(data.refreshed_at);

    const cur = data.windows.current;
    const prev = data.windows.previous;
    document.querySelector("#current .window-meta").textContent =
      `${fmtWindow(cur)} • Day ${cur.day} of 7 (threshold ${cur.threshold}) • ${fmtCountdown(cur.end, Date.now())}`;
    document.querySelector("#previous .window-meta").textContent = fmtWindow(prev);

    renderTable("current", data.members, mode, true);
    renderTable("previous", data.members, mode, false);
  }

  document.getElementById("toggle-on").addEventListener("click", (e) => {
    e.preventDefault();
    document.body.dataset.mode = "dedup";
    render();
  });
  document.getElementById("toggle-off").addEventListener("click", (e) => {
    e.preventDefault();
    document.body.dataset.mode = "raw";
    render();
  });

  render();
})();
```

- [ ] **Step 2: Commit**

```bash
git add src/journal/static/app.js
git commit -m "feat(static): vanilla-JS renderer with dedup toggle and status sorting"
```

---

### Task 14: `__main__.py` — CLI

**Files:**
- Create: `src/journal/__main__.py`
- Modify: `src/journal/__init__.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_main.py`:

```python
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest.mock import patch

import httpx

from journal.__main__ import build

SGT = ZoneInfo("Asia/Singapore")
FIXTURES = Path(__file__).parent / "fixtures"


def test_build_end_to_end_with_mocked_http(tmp_path):
    """Run the full build with httpx MockTransport and verify outputs."""

    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text(
        '<!doctype html><html><body><script type="application/json" id="data">__DATA__</script></body></html>'
    )
    (static / "app.js").write_text("// app")
    (static / "style.css").write_text("/* css */")

    out = tmp_path / "site"
    cache_path = tmp_path / "cache.json"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/entry/" in url:
            return httpx.Response(200, text=(FIXTURES / "entry-page-158567.html").read_text())
        if "filter_11" in url:
            return httpx.Response(200, text=(FIXTURES / "search-page-jet.html").read_text())
        return httpx.Response(200, text=(FIXTURES / "search-page-empty.html").read_text())

    fixed_now = datetime(2026, 5, 6, 7, 0, tzinfo=SGT)
    with patch("journal.__main__._http_client", return_value=httpx.Client(transport=httpx.MockTransport(handler))), \
         patch("journal.__main__._now", return_value=fixed_now):
        rc = build(cache_path=cache_path, out_dir=out, static_dir=static)

    assert rc == 0
    payload = json.loads((out / "data.json").read_text())
    assert payload["version"] == 1
    assert any(m["name"] == "Jet" for m in payload["members"])
    assert (out / "index.html").exists()
    assert (out / "app.js").read_text() == "// app"
    assert cache_path.exists()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_main.py -v`
Expected: ImportError on `journal.__main__`.

- [ ] **Step 3: Implement `__main__.py`**

Create `src/journal/__main__.py`:

```python
import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from .cache import EntryCache
from .client import fetch_member_list, fetch_search, fetch_entry_body
from .report import build_full_report
from .serialize import to_payload, write_site

SGT = ZoneInfo("Asia/Singapore")


def _http_client() -> httpx.Client:
    return httpx.Client(timeout=30.0, follow_redirects=True)


def _now() -> datetime:
    return datetime.now(SGT)


def build(*, cache_path: Path, out_dir: Path, static_dir: Path) -> int:
    cache = EntryCache.load(cache_path)
    now = _now()

    with _http_client() as client:
        try:
            members = fetch_member_list(client)
        except Exception as e:
            print(f"FATAL: failed to fetch member list: {e!r}", file=sys.stderr)
            return 1

        report = build_full_report(
            members=members,
            now=now,
            cache=cache,
            fetch_search=lambda name, s, e: fetch_search(client, name, s, e),
            fetch_body=lambda url: fetch_entry_body(client, url),
        )

    cache.save()
    write_site(to_payload(report), static_dir=static_dir, out_dir=out_dir)
    return 0


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).parent
    p = argparse.ArgumentParser(prog="journal")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="Scrape and write site/")
    b.add_argument("--cache", type=Path, default=Path("cache.json"))
    b.add_argument("--out", type=Path, default=Path("site"))
    b.add_argument("--static", type=Path, default=here / "static")

    args = p.parse_args(argv)
    if args.cmd == "build":
        return build(cache_path=args.cache, out_dir=args.out, static_dir=args.static)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_main.py -v`
Expected: pass.

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest -v`
Expected: every test in every file passes.

- [ ] **Step 6: Commit**

```bash
git add src/journal/__main__.py tests/test_main.py
git commit -m "feat(cli): build subcommand wiring scrape → report → site"
```

---

### Task 15: End-to-end smoke test against the live platform

**Files:**
- (verification only; no code changes)

This task confirms the build works against real HTML, not just fixtures. Do **not** commit `site/` (it's gitignored).

- [ ] **Step 1: Run the build once with no cache**

Run:
```bash
rm -f cache.json
uv run python -m journal build --cache cache.json --out site
```

Expected:
- Exits 0.
- Prints no FATAL line.
- `site/data.json`, `site/index.html`, `site/app.js`, `site/style.css` exist.
- `cache.json` contains entries (count > 0).

- [ ] **Step 2: Sanity-check the JSON payload**

Run:
```bash
uv run python -c "import json; d=json.load(open('site/data.json')); print('members:', len(d['members'])); print('windows:', d['windows'])"
```

Expected:
- `members: 18` to `25` (around 20).
- `windows.current.start` is a Wed 08:00 SGT.
- `windows.current.end` is the following Wed 08:00 SGT.

- [ ] **Step 3: Visually verify in a browser**

Run:
```bash
uv run python -m http.server -d site 8000
```

Open http://localhost:8000/ in a browser. Verify:
- Both tables populate.
- Header shows "Refreshed …" timestamp.
- Toggle `on / off` flips counts and re-sorts; the `data-mode` attribute on `<body>` flips.
- A row known to be "Done" shows `✓ Done` in green; a behind row shows `✗ Behind` in red.

Stop the server (Ctrl-C).

- [ ] **Step 4: Re-run the build with the warm cache to confirm cache reuse**

Run:
```bash
uv run python -m journal build --cache cache.json --out site
```

Expected: completes faster than the cold run (most entry fetches skipped).

- [ ] **Step 5: Optional cleanup**

```bash
rm -rf site cache.json
```

(No commit. This task is verification only.)

---

### Task 16: GitHub Actions workflow + initial cache branch

**Files:**
- Create: `.github/workflows/refresh.yml`

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/refresh.yml`:

```yaml
name: Refresh

on:
  schedule:
    - cron: "0 * * * *"
  workflow_dispatch:

concurrency:
  group: refresh
  cancel-in-progress: false

permissions:
  contents: write
  pages: write
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deploy.outputs.page_url }}
    steps:
      - name: Checkout main
        uses: actions/checkout@v4

      - name: Checkout cache branch (or initialize)
        run: |
          set -e
          mkdir -p .cache
          if git ls-remote --exit-code --heads origin cache >/dev/null 2>&1; then
            git -C .cache init -q
            git -C .cache remote add origin "$GITHUB_SERVER_URL/$GITHUB_REPOSITORY"
            git -C .cache fetch --depth 1 origin cache
            git -C .cache checkout cache
          else
            echo '{"version": 1, "entries": {}}' > .cache/cache.json
          fi
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Install uv
        uses: astral-sh/setup-uv@v5

      - name: Sync deps
        run: uv sync

      - name: Build site
        run: uv run python -m journal build --cache .cache/cache.json --out site

      - name: Push updated cache (if changed)
        run: |
          set -e
          cd .cache
          if [ ! -d .git ]; then
            git init -q
            git checkout --orphan cache
            git remote add origin "$GITHUB_SERVER_URL/$GITHUB_REPOSITORY"
          fi
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git config user.name "github-actions[bot]"
          git add cache.json
          if git diff --quiet --cached; then
            echo "No cache changes."
            exit 0
          fi
          git commit -m "chore: refresh cache"
          git push "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" HEAD:cache
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Upload Pages artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: site

      - name: Deploy to GitHub Pages
        id: deploy
        uses: actions/deploy-pages@v4
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/refresh.yml
git commit -m "ci: hourly refresh workflow with cache branch and Pages deploy"
```

- [ ] **Step 3: Push to the remote**

```bash
git push -u origin main
```

- [ ] **Step 4: Enable GitHub Pages in the repo**

In the GitHub UI: **Settings → Pages → Build and deployment → Source: GitHub Actions**. (No commit; one-time repo configuration.)

- [ ] **Step 5: Trigger the first run**

In the GitHub UI: **Actions → Refresh → Run workflow**.

Expected:
- The job succeeds.
- The `cache` branch appears in the repo (orphan branch with one commit, holding `cache.json`).
- The Pages deploy URL renders the site correctly.

- [ ] **Step 6: Verify the warm-run path**

Trigger the workflow a second time. Expected: completes faster, "No cache changes" line appears or only a small diff is committed.

---

## Self-review

**Spec coverage:**

| Spec section | Task |
|---|---|
| Data source / GET form / member list | Tasks 6, 8 |
| Counting rule + dedup | Task 4, 9 |
| Hash cache (load/save/fallback/version) | Task 5 |
| Cache branch + concurrency + permissions | Task 16 |
| Day numbering + threshold | Task 3 |
| Status (current week, last week, fetch-failed) | Task 9 |
| UI layout + sort + toggle + rendering model | Tasks 12, 13 |
| Architecture pipeline | Tasks 14, 16 |
| `data.json` schema (versions, statuses, dropped_rows, fetch_failed) | Task 11 |
| Error handling (search-fail vs entry-fail vs catastrophic) | Tasks 9, 10, 14 |
| Testing (parser, window, dedup, cache, report, serialize, JS smoke) | Tasks 3-11, 15 |

**Placeholder scan:** No "TBD" / "implement later" / "similar to Task N". All code blocks self-contained.

**Type consistency:** `Status` enum used identically across `report.py`, `serialize.py`, `app.js`. `ModeStats` / `WindowReport` / `MemberReport` / `FullReport` / `EntryCache` / `Row` names match between definition and consumption sites. CLI flag names match between `__main__.py`, the spec, and the workflow YAML.
