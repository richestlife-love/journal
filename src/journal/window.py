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
