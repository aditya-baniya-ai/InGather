from datetime import UTC, date, datetime, time, timedelta

from app.services.clock import as_utc, daily_windows, intersect, merge, minutes


def utc(*args):
    return datetime(*args, tzinfo=UTC)


def test_naive_datetimes_are_treated_as_utc():
    assert as_utc(datetime(2027, 1, 17, 22)) == utc(2027, 1, 17, 22)
    assert as_utc(datetime.fromisoformat("2027-01-17T17:00:00-05:00")) == utc(2027, 1, 17, 22)


def test_after_5pm_new_york_in_winter_is_2200_utc():
    windows = daily_windows("America/New_York", date(2027, 1, 17), date(2027, 1, 19), time(17), time(22))
    assert windows[0] == (utc(2027, 1, 17, 22), utc(2027, 1, 18, 3))
    assert len(windows) == 3


def test_dst_spring_forward_shifts_utc_by_one_hour():
    # US DST starts 2027-03-14: 5pm local is 22:00 UTC before, 21:00 UTC after
    windows = daily_windows("America/New_York", date(2027, 3, 13), date(2027, 3, 14), time(17), time(19))
    assert windows[0][0] == utc(2027, 3, 13, 22)
    assert windows[1][0] == utc(2027, 3, 14, 21)
    assert all(e - s == timedelta(hours=2) for s, e in windows)


def test_dst_fall_back_evening_across_zones():
    # 2027-11-07 US fall back: 6pm Chicago == 7pm New York on both sides of the change
    ny = daily_windows("America/New_York", date(2027, 11, 6), date(2027, 11, 7), time(19), time(21))
    chi = daily_windows("America/Chicago", date(2027, 11, 6), date(2027, 11, 7), time(18), time(19))
    common = intersect(ny, chi)
    assert minutes(common) == 120
    assert common[1][0] == utc(2027, 11, 8, 0)


def test_overnight_window_crosses_midnight():
    [(s, e)] = daily_windows("America/New_York", date(2027, 1, 17), date(2027, 1, 17), time(22), time(1))
    assert e - s == timedelta(hours=3)


def test_merge_and_intersect():
    a = [(utc(2027, 1, 1, 10), utc(2027, 1, 1, 12)), (utc(2027, 1, 1, 11), utc(2027, 1, 1, 13))]
    assert merge(a) == [(utc(2027, 1, 1, 10), utc(2027, 1, 1, 13))]
    b = [(utc(2027, 1, 1, 12, 30), utc(2027, 1, 1, 15))]
    assert intersect(a, b) == [(utc(2027, 1, 1, 12, 30), utc(2027, 1, 1, 13))]
    assert intersect(a, [(utc(2027, 1, 1, 13), utc(2027, 1, 1, 14))]) == []  # touching is not overlap
