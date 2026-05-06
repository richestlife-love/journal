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
- A boolean toggle disables dedup and falls back to raw row count. The toggle is exposed in the UI. **Default: dedup on.**

The truncated preview in the search-results table is **not** sufficient for dedup — we fetch each in-window entry's full page to extract the body.

### Hash cache

Entries on the source platform are immutable (assumed). We cache the normalized-body hash by entry ID across runs and never invalidate it. The cache is monotonic-add-only.

- Storage: a single `cache.json` file on a dedicated `cache` orphan branch in the same repo.
- Schema: `{ "version": 1, "entries": { "<entry_id>": "sha256:<hex>" } }`.
- Lookup flow per row: if `entry_id` is in the cache, reuse the hash; otherwise fetch the entry page, compute the hash, write it back.
- After warm-up, only new entries are fetched: typically **0–5 fetches per hourly run**, peaking at **20–40** during the Tue-night → Wed-morning rush. Cold first run fetches ~400–600.
- No TTL, no `fetched_at`, no pruning. Cache size at scale is negligible (one short string per entry).
- **First-run / missing-cache fallback**: if the `cache` branch does not exist, or `cache.json` is missing/malformed/wrong `version`, the build proceeds with an empty in-memory cache and writes a fresh `cache.json` at the end. No error.
- **Workflow concurrency**: `concurrency: { group: refresh, cancel-in-progress: false }` so the orphan branch has only one writer at a time.
- **Workflow permissions**: needs `permissions: { contents: write, pages: write, id-token: write }` — `contents: write` for the cache-branch push, the latter two for the Pages deploy.

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

**Sort order (each table)**: `⚠ Fetch failed` first (alphabetical), then `✗ Behind` by ascending count then alphabetical, then `→ On track` by ascending count, then `✓ Done` alphabetical. Members with partial entry-fetch failures (the row-level `⚠` indicator) are not promoted by the sort — they sort by their surviving count under the normal status bucket.

**Rendering model**: the page is rendered entirely in the browser. The Python build emits a static `index.html` skeleton (header chrome, two empty `<section>`s for the two tables, the toggle link, and a `<script type="application/json" id="data">…</script>` tag carrying both deduped and raw stats). On load, ~30 lines of vanilla JS parse the JSON and populate both tables. No framework, no Jinja2.

**Dedup toggle**: clicking `[on]/[off]` re-runs the same render function with the alternate count field. State held in a `data-mode` attribute on `<body>` for CSS hooks; default is `dedup`.

**Mobile**: tables remain full-width with horizontal scroll if needed. No special mobile design beyond reasonable CSS defaults.

## Architecture

**Single static site, regenerated on a schedule.**

```
GitHub Actions (cron + manual, concurrency: refresh)
  ├── checkout main → working dir
  ├── checkout cache branch → .cache/
  └── uv run python -m journal build --cache .cache/cache.json
       ├── load cache.json (entry_id → hash)
       ├── fetch SG member list (filter_11 options)
       ├── for each member:
       │     ├── fetch search results for [last completed week .. current week]
       │     ├── parse rows; assign each to a window
       │     └── for each in-window row:
       │           ├── if entry_id in cache → reuse hash
       │           └── else → fetch entry page, hash body, write to cache
       ├── dedup per (member, window) by body hash
       ├── compute count, last submission, status (per dedup mode)
       ├── save cache.json
       └── write site/data.json + copy static/{index.html,app.js,style.css} → site/
  ├── commit + push cache.json to cache branch (if changed)
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
  cache.py             # entry_id → body-hash JSON cache (monotonic, immutable entries assumed)
  window.py            # SGT 8am-Wed window math, day numbering, threshold
  dedup.py             # body normalization (HTML strip + whitespace collapse) + grouping
  report.py            # per-member aggregate (count, last_submission, status) for both modes
  serialize.py         # build the JSON payload and copy static assets to site/
  static/
    index.html         # skeleton: header, two empty <section>s, embedded JSON tag, <script src="app.js">
    app.js             # ~30 lines vanilla JS — parse embedded JSON, render rows, wire toggle
    style.css
tests/
  fixtures/
    search-page.html        # captured from real platform
    entry-page.html         # captured from real platform
  test_client.py
  test_cache.py
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
- `cache.py` — `EntryCache.load(path) -> EntryCache`, `get(entry_id) -> str | None`, `put(entry_id, hash_) -> None`, `save() -> None`. JSON file backed. No invalidation. Knows nothing about windows or members.
- `window.py` — time-only logic: `current_window(now) -> (start, end)`, `previous_window(now) -> (start, end)`, `day_number(t, window) -> int (1..7)`, `threshold(t, window) -> int (0..7)`. All datetimes are SGT-aware (`zoneinfo("Asia/Singapore")`).
- `dedup.py` — `normalize_body(html_or_text: str) -> str`, `body_hash(text: str) -> str`, `dedup_count(hashes: list[str]) -> int`. Pure functions; takes already-fetched-or-cached hashes.
- `report.py` — composes the above to produce, per member per window, both deduped and raw counts, last-submission timestamp, and status. Calls `cache.get` first; only invokes `client.fetch_entry_body` on cache miss. Returns plain Python data (no formatting).
- `serialize.py` — `to_payload(report, now) -> dict` building the JSON payload (windows, refresh timestamp, day-N + threshold, per-member rows for both modes), and `write_site(payload, static_dir, out_dir)` which writes `data.json` and copies `index.html`, `app.js`, `style.css`. All human-facing formatting (relative times, "Day N of 7", deadline countdown) is done in JS, not here — this module deals only in machine-readable values (ISO timestamps, integers).
- `static/app.js` — runs on page load. Reads the JSON from `<script type="application/json" id="data">`, computes display strings (relative time, countdown), builds two tables, wires the dedup toggle to re-render in the alternate mode. Self-contained; no module loader.
- `__main__.py` — wires the pieces, handles CLI flags (`--cache <path>`, `--out <dir>`, `--static <dir>`), exits non-zero on catastrophic failures (e.g. cannot reach the platform at all).

## Error handling

Failures are graded by what failed:

- **Search-page fetch fails for a member** (i.e. we can't even list their submissions). The member's row in both tables renders `?/7` with status `⚠ Fetch failed` and a tooltip carrying the error. Sorted to the top.
- **Entry-page fetch fails for a single row** (search succeeded, but one entry page errored). The row is dropped from that member's count for this run and a small `⚠` indicator appears next to the count (e.g. `4/7 ⚠`) with a tooltip listing the count of dropped rows. The member's status is still computed from the surviving rows. Count is therefore a lower bound, not an overcount; this is intentional. The cache is **not** populated for the failed entry, so the next run will retry.
- **Catastrophic failure** (cannot fetch the search-page list of members at all, cannot parse `filter_11`) exits non-zero. The previous deployed page remains visible. The "Refreshed at …" timestamp shows the staleness.
- All failures are logged to GitHub Actions output.
- The HTML always includes the refresh timestamp prominently so visitors never get a silently stale view.

## Testing

- **Parser tests** use captured real HTML in `tests/fixtures/` (we already have one for member "Jet" — to be saved as a fixture). Snapshot the parsed output.
- **Window math tests** cover boundary cases: exactly 08:00 SGT on Wed (window roll), DST irrelevant for Singapore but verified, day-N transitions at each 08:00.
- **Dedup tests** cover: identical text, identical text with different whitespace, identical text with different HTML wrapping, two truly distinct journals.
- **Cache tests** cover: hit returns stored hash without invoking fetcher, miss invokes fetcher and persists, save+reload round-trips, malformed/missing file degrades to empty cache.
- **Report tests** verify status transitions across all (count, threshold) cells.
- **Serialize tests** snapshot the `data.json` payload shape (keys, types, value ranges) given a fixed `report` and `now`. Format-of-display strings live in JS, so they're not exercised here.
- **JS rendering**: not exercised by the Python test suite in v1. Verified by a manual smoke test (`python -m http.server` over `site/` after a build, open in a browser, confirm both tables render and the toggle flips counts/sorts). A headless-browser test can be added later if regressions appear.
- No live network in tests. The HTTP layer is mocked or the parser is fed fixtures directly.

## Out of scope (not in v1)

- Per-day grid view (one column per day).
- Other regions (filter_7..10, filter_12, filter_13). The code path generalizes trivially when needed.
- Authentication, write actions, or member-facing notifications.
- Historical archive beyond the last completed week.

## Dependencies

- Runtime: `httpx`, `selectolax`. Stdlib `zoneinfo`, `hashlib`, `datetime`, `json`, `shutil`.
- Dev: `pytest`.
- Python 3.14, managed by `uv` (already pinned in `.python-version` and `pyproject.toml`).
