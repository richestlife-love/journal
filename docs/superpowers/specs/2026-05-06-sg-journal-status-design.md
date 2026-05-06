# RichestLife SG — Journal Submission Status Tracker

**Status:** approved 2026-05-06

## Purpose

A public static website that shows, at a glance, which of the ~20 Singapore RichestLife organizers have met the weekly submission target on https://writexperience.richestlife.com/sg-check-experience/. The target is **at least 7 journal submissions per week**, where a week runs from **8:00 SGT (UTC+8) on Wednesday to 8:00 SGT on the following Wednesday**.

The page is consumed by SG admins to nudge members who are behind before each Wednesday 8am deadline, and to confirm the result immediately after the deadline.

## Data source

The source platform is a WordPress site using the GravityView plugin. The query page at `/sg-check-experience/` accepts a plain GET form with these parameters:

| Param | Meaning |
|---|---|
| `filter_3[start]` | start date, format `MM/DD/YYYY` (calendar day, not time) |
| `filter_3[end]` | end date, format `MM/DD/YYYY` (calendar day, not time) |
| `filter_11` | Singapore organizer name (one of the dropdown options) |
| `mode=all` | match all filters |

The response is HTML containing a result table with rows of:

| Column | HTML class | Meaning |
|---|---|---|
| 時間 | `gv-field-7-custom` | submission timestamp, formatted `YYYY-MM-DD at HH:MM` (SGT) |
| 看心得全文請點選日期 | `gv-field-7-3` | clickable link `<a href=".../entry/<id>/">YYYY-MM-DD</a>` — the date here matches the submission date and is **not** a user-chosen journal date |
| 主持人 | `gv-field-7-custom` | organizer name |
| 心得 | `gv-field-7-15` | a truncated journal preview |

There is **no structured "journal-chosen date" field**. Body-text date conventions are unreliable (per stakeholder), so all date logic uses the submission timestamp from the 時間 column.

The `filter_11` `<select>` on the page contains the canonical, current list of SG organizers. We parse it on every refresh so adds/removes track automatically.

No authentication is required. The site's `robots.txt`-equivalent uses `noindex, nofollow`, but content is publicly fetchable.

## Counting rule

A member's submission count for a given window is the number of **distinct journal contents** they submitted with timestamps inside the window.

- **Window** is half-open: `[Wed 08:00 SGT, next Wed 08:00 SGT)`.
- **Distinct content** is defined by hashing the **full plain-text body** of the journal entry (fetched from each row's entry URL — column 2's `<a href>`), after normalizing whitespace and stripping HTML.
- A boolean toggle disables dedup and falls back to raw row count. The toggle is exposed in the UI.

The truncated preview in the search-results table is **not** sufficient for dedup — we fetch each in-window entry's full page to extract the body.

## Day numbering and "on track" threshold

A "day" is a 24-hour block from 08:00 SGT to 08:00 SGT. Within a window:

| Day # | Start (SGT) | End (SGT) |
|---|---|---|
| 1 | window-start Wed 08:00 | Thu 08:00 |
| 2 | Thu 08:00 | Fri 08:00 |
| 3 | Fri 08:00 | Sat 08:00 |
| 4 | Sat 08:00 | Sun 08:00 |
| 5 | Sun 08:00 | Mon 08:00 |
| 6 | Mon 08:00 | Tue 08:00 |
| 7 | Tue 08:00 | window-end Wed 08:00 (deadline) |

**Threshold** at observation time `T` inside the window:

```
threshold(T) = number of fully-completed days from window-start to T
             = floor((T - window_start) / 24h)   # values 0..7
```

| Time (SGT) within current window | Day | Threshold |
|---|---|---|
| Wed 08:00 → Thu 07:59 | Day 1 | 0 |
| Thu 08:00 → Fri 07:59 | Day 2 | 1 |
| Fri 08:00 → Sat 07:59 | Day 3 | 2 |
| Sat 08:00 → Sun 07:59 | Day 4 | 3 |
| Sun 08:00 → Mon 07:59 | Day 5 | 4 |
| Mon 08:00 → Tue 07:59 | Day 6 | 5 |
| Tue 08:00 → Wed 07:59 | Day 7 | 6 |
| Wed 08:00 (deadline) | window closed | 7 |

## Status

`count` is the active-mode count (deduped count when the dedup toggle is on, raw row count when off). Status is computed independently for each mode so toggling the UI re-evaluates statuses without re-rendering.

For the **current in-progress week** (with `threshold` as defined above):

| Condition | Status |
|---|---|
| `count >= 7` | **✓ Done** |
| `count < 7 && count > threshold` | **→ On track** |
| `count <= threshold` | **✗ Behind** |

Note: this is the strict-pace interpretation. At each 8am SGT day boundary the threshold steps up, and members are Behind until they make a *new* submission to overtake it. At Wed 08:00 (threshold 0), a member with 0 submissions is already Behind.

For the **last completed week**, the window has closed so only two states apply:

| Condition | Status |
|---|---|
| `count >= 7` | **✓ Done** |
| `count < 7` | **✗ Behind** |

A 4th display-only state, **⚠ Fetch failed**, is shown for any member whose data could not be retrieved this run (see Error handling). It is not produced by the rules above; rows in this state render `?/7` and are sorted to the very top.

## UI layout

A single static HTML page with two stacked tables.

```
┌─ Header ─────────────────────────────────────────────────┐
│ RichestLife SG — Journal Submission Status               │
│ Refreshed YYYY-MM-DD HH:MM SGT  •  Dedup: [on] off       │
└──────────────────────────────────────────────────────────┘

▌ Current week  (Wed YYYY-MM-DD 08:00 → Wed YYYY-MM-DD 08:00 SGT)
▌ Deadline in Xd Yh   •   Day N of 7 (threshold: T)

┌──────────┬──────────────┬────────────┬──────────────────┐
│ Name     │ Submissions  │ Status     │ Last submission  │
├──────────┼──────────────┼────────────┼──────────────────┤
│ Aillyn   │ 0/7          │ ✗ Behind   │ —                │
│ Same     │ 2/7          │ ✗ Behind   │ 3 hours ago      │
│ Lorene   │ 4/7          │ → On track │ 12 minutes ago   │
│ Jet      │ 7/7          │ ✓ Done     │ 7 minutes ago    │
└──────────┴──────────────┴────────────┴──────────────────┘

▌ Last completed week  (Wed YYYY-MM-DD 08:00 → Wed YYYY-MM-DD 08:00 SGT)
   [same shape, but status only Done/Behind, no countdown]
```

**Column details**

- *Name* — value from `filter_11` option. Displayed as text.
- *Submissions* — `count/7`. With dedup off, `count` can exceed 7; in that case it still displays as e.g. `9/7`. The denominator is the target, not a cap.
- *Status* — `✓ Done`, `→ On track`, or `✗ Behind` (current week); `✓ Done` or `✗ Behind` (last completed week).
- *Last submission* — relative time (e.g. "12 minutes ago", "3 hours ago", "yesterday at 14:32"). `—` if no submissions in window.

**Sort order (each table)**: `⚠ Fetch failed` first (alphabetical), then `✗ Behind` by ascending count then alphabetical, then `→ On track` by ascending count, then `✓ Done` alphabetical.

**Dedup toggle**: a small `[on]/[off]` link in the header flips between deduped and raw counts. Implementation: data for both views is embedded once as JSON in a `<script type="application/json">` tag, and ~10 lines of vanilla JS swap the displayed numbers and re-sort. No framework.

**Mobile**: tables remain full-width with horizontal scroll if needed. No special mobile design beyond reasonable CSS defaults.

## Architecture

**Single static site, regenerated on a schedule.**

```
GitHub Actions (cron + manual)
  └── uv run python -m journal build
       ├── fetch SG member list (filter_11 options)
       ├── for each member:
       │     ├── fetch search results for [last completed week .. current week]
       │     ├── parse rows; assign each to a window
       │     └── for each in-window row, fetch entry page for full body
       ├── dedup per (member, window) by body hash
       ├── compute count, last submission, status (per dedup mode)
       └── render site/index.html and site/data.json
  └── actions/deploy-pages → GitHub Pages
```

**Refresh cadence**: hourly cron + `workflow_dispatch` for manual refresh. The header shows the refresh timestamp. More aggressive cron is a one-line config change later if needed.

**No server, no database.** Each run rebuilds from scratch from public HTML.

## Project structure

```
src/journal/
  __init__.py
  __main__.py          # CLI: `uv run python -m journal build [--out site]`
  client.py            # httpx fetch + selectolax parse for search page and entry page
  window.py            # SGT 8am-Wed window math, day numbering, threshold
  dedup.py             # body normalization (HTML strip + whitespace collapse) + grouping
  report.py            # per-member aggregate (count, last_submission, status) for both modes
  render.py            # jinja2 → site/index.html + site/data.json
  templates/
    index.html.j2
  static/
    style.css
tests/
  fixtures/
    search-page.html        # captured from real platform
    entry-page.html         # captured from real platform
  test_client.py
  test_window.py
  test_dedup.py
  test_report.py
.github/workflows/
  refresh.yml          # cron + workflow_dispatch → build → deploy-pages
docs/superpowers/specs/
  2026-05-06-sg-journal-status-design.md   # this file
site/                   # build output, gitignored
```

## Module responsibilities

- `client.py` — pure HTTP/HTML layer. Functions: `fetch_member_list() -> list[str]`, `fetch_search(name, start_date, end_date) -> list[Row]`, `fetch_entry_body(entry_url) -> str`. `Row` carries `submission_ts: datetime` (SGT-aware), `entry_id: str`, `entry_url: str`, `preview: str`. No business logic, no time-window filtering.
- `window.py` — time-only logic: `current_window(now) -> (start, end)`, `previous_window(now) -> (start, end)`, `day_number(t, window) -> int (1..7)`, `threshold(t, window) -> int (0..7)`. All datetimes are SGT-aware (`zoneinfo("Asia/Singapore")`).
- `dedup.py` — `normalize_body(html_or_text: str) -> str`, `dedup_count(bodies: list[str]) -> int`. Pure functions over already-fetched bodies.
- `report.py` — composes the above to produce, per member per window, both deduped and raw counts, last-submission timestamp, and status.
- `render.py` — jinja2 template + JSON serializer. Owns formatting (e.g. relative time, "Day N of 7", deadline countdown).
- `__main__.py` — wires the pieces, handles CLI flags, exits non-zero on catastrophic failures (e.g. cannot reach the platform at all).

## Error handling

- **Per-member fetch failure** does not fail the run. The row renders as `?/7` with status `⚠ Fetch failed` and a tooltip describing the error. Failures are logged to GitHub Actions output.
- **Catastrophic failure** (cannot fetch the search page itself, cannot parse member list) exits non-zero — the previous deployed page remains visible, with its older "Refreshed at …" timestamp making the staleness obvious.
- The HTML always includes the refresh timestamp prominently so visitors never get a silently stale view.

## Testing

- **Parser tests** use captured real HTML in `tests/fixtures/` (we already have one for member "Jet" — to be saved as a fixture). Snapshot the parsed output.
- **Window math tests** cover boundary cases: exactly 08:00 SGT on Wed (window roll), DST irrelevant for Singapore but verified, day-N transitions at each 08:00.
- **Dedup tests** cover: identical text, identical text with different whitespace, identical text with different HTML wrapping, two truly distinct journals.
- **Report tests** verify status transitions across all (count, threshold) cells.
- No live network in tests. The HTTP layer is mocked or the parser is fed fixtures directly.

## Out of scope (not in v1)

- Per-day grid view (one column per day).
- Caching entry bodies across runs (each run re-fetches).
- Other regions (filter_7..10, filter_12, filter_13). The code path generalizes trivially when needed.
- Authentication, write actions, or member-facing notifications.
- Historical archive beyond the last completed week.

## Dependencies

- Runtime: `httpx`, `selectolax`, `jinja2`. Stdlib `zoneinfo`, `hashlib`, `datetime`.
- Dev: `pytest`.
- Python 3.14, managed by `uv` (already pinned in `.python-version` and `pyproject.toml`).
