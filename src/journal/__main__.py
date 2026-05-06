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
