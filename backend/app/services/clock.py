"""Time helpers. Everything is stored and compared in UTC; IANA zones are only used at the edges."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

Interval = tuple[datetime, datetime]


def as_utc(dt: datetime) -> datetime:
    """SQLite hands back naive datetimes; treat naive values as UTC."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def daily_windows(tz: str, start: date, end: date, begin: time, finish: time) -> list[Interval]:
    """Local wall-clock window on each day (DST-correct), converted to UTC."""
    zone = ZoneInfo(tz)
    out, day = [], start
    while day <= end:
        s = datetime.combine(day, begin, zone)
        e = datetime.combine(day if finish > begin else day + timedelta(days=1), finish, zone)
        out.append((as_utc(s), as_utc(e)))
        day += timedelta(days=1)
    return out


def merge(intervals: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for s, e in sorted((as_utc(s), as_utc(e)) for s, e in intervals):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def intersect(a: list[Interval], b: list[Interval]) -> list[Interval]:
    out = [(max(s1, s2), min(e1, e2)) for s1, e1 in merge(a) for s2, e2 in merge(b)]
    return merge([(s, e) for s, e in out if e > s])


def minutes(intervals: list[Interval]) -> int:
    return int(sum((e - s).total_seconds() for s, e in intervals) // 60)
