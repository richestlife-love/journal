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
    assert threshold(sgt(2026, 4, 29, 8, 0), win) == 0  # Day 1 starts
    assert threshold(sgt(2026, 4, 30, 7, 59), win) == 0  # still Day 1
    assert threshold(sgt(2026, 4, 30, 8, 0), win) == 1  # Day 2 starts
    assert threshold(sgt(2026, 5, 1, 8, 0), win) == 2
    assert threshold(sgt(2026, 5, 5, 8, 0), win) == 6
    assert threshold(sgt(2026, 5, 6, 7, 59), win) == 6
    assert threshold(sgt(2026, 5, 6, 8, 0), win) == 7  # window closed
