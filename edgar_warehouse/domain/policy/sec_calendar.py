"""Calendar helpers for SEC business-date logic."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

_ET_ZONE = ZoneInfo("America/New_York")


def is_business_day(value: date) -> bool:
    return value.weekday() < 5 and value not in us_federal_holidays(value.year)


def expected_available_at(business_date: date) -> datetime:
    next_day = business_date + timedelta(days=1)
    local = datetime(next_day.year, next_day.month, next_day.day, 6, 0, 0, tzinfo=_ET_ZONE)
    return local.astimezone(UTC)


def next_business_day(value: date) -> date:
    candidate = value + timedelta(days=1)
    while not is_business_day(candidate):
        candidate += timedelta(days=1)
    return candidate


def previous_business_day(value: date) -> date:
    candidate = value - timedelta(days=1)
    while not is_business_day(candidate):
        candidate -= timedelta(days=1)
    return candidate


def latest_eligible_business_date(now: datetime) -> date:
    candidate = previous_business_day(now.astimezone(_ET_ZONE).date() + timedelta(days=1))
    while expected_available_at(candidate) > now:
        candidate = previous_business_day(candidate)
    return candidate


def date_range(start: date, end: date) -> list[date]:
    values: list[date] = []
    current = start
    while current <= end:
        values.append(current)
        current += timedelta(days=1)
    return values


def us_federal_holidays(year: int) -> set[date]:
    return {
        observed_date(date(year, 1, 1)),
        nth_weekday(year, 1, 0, 3),
        nth_weekday(year, 2, 0, 3),
        last_weekday(year, 5, 0),
        observed_date(date(year, 6, 19)),
        observed_date(date(year, 7, 4)),
        nth_weekday(year, 9, 0, 1),
        nth_weekday(year, 10, 0, 2),
        observed_date(date(year, 11, 11)),
        nth_weekday(year, 11, 3, 4),
        observed_date(date(year, 12, 25)),
    }


def observed_date(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def nth_weekday(year: int, month: int, weekday: int, ordinal: int) -> date:
    current = date(year, month, 1)
    while current.weekday() != weekday:
        current += timedelta(days=1)
    return current + timedelta(days=7 * (ordinal - 1))


def last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        current = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        current = date(year, month + 1, 1) - timedelta(days=1)
    while current.weekday() != weekday:
        current -= timedelta(days=1)
    return current
