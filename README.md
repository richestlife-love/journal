# RichestLife Journal Submission Status Tracker

A tiny static site that tracks submission statuses for the RichestLife journal. The build scrapes the journal's search pages, dedupes and caches entries, and renders a paginated week view to `site/`.

## Local build

```sh
uv sync
uv run python -m journal build --cache cache.json --out site
```

Then open `site/index.html`. Flags:

- `--cache` — path to the JSON cache (created on first run)
- `--out` — output directory

## Tests

```sh
uv run pytest
```

## Deploy

Hosted on GitHub Pages via `.github/workflows/refresh.yml`:

- **Schedule** — every 5 minutes; redeploys only when `cache.json` changes
- **Push to `main`** — always rebuilds and redeploys
- **Manual** — `workflow_dispatch` from the Actions tab

Concurrency group `refresh` cancels any in-flight run when a newer one starts. The cache is persisted on a dedicated `cache` branch.

## Layout

```text
src/journal/
  __main__.py    # CLI entry: `python -m journal build`
  client.py      # HTTP fetch
  window.py      # Date-window logic
  cache.py       # JSON cache load/save
  dedup.py       # Entry deduping
  report.py      # Aggregation
  serialize.py   # Payload for the static site
  static/        # index.html, app.js, style.css
```
