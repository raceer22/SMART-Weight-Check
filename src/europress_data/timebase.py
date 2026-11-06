"""Time axis (hourly, UTC storage, Europe/Helsinki local logic) and Finnish public holidays."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd


def easter_sunday(year: int) -> dt.date:
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(year, month, day)


def finnish_holidays(year: int) -> dict[dt.date, str]:
    """Finnish public holidays plus Christmas Eve / Midsummer Eve (de facto closures)."""
    es = easter_sunday(year)
    hol = {
        dt.date(year, 1, 1): "New Year's Day",
        dt.date(year, 1, 6): "Epiphany",
        es - dt.timedelta(days=2): "Good Friday",
        es + dt.timedelta(days=1): "Easter Monday",
        dt.date(year, 5, 1): "May Day",
        es + dt.timedelta(days=39): "Ascension Day",
        dt.date(year, 12, 6): "Independence Day",
        dt.date(year, 12, 24): "Christmas Eve",
        dt.date(year, 12, 25): "Christmas Day",
        dt.date(year, 12, 26): "St Stephen's Day",
    }
    # Midsummer Eve: Friday between 19 and 25 June; Midsummer Day the Saturday after
    for d in range(19, 26):
        day = dt.date(year, 6, d)
        if day.weekday() == 4:
            hol[day] = "Midsummer Eve"
            hol[day + dt.timedelta(days=1)] = "Midsummer Day"
    # All Saints' Day: Saturday between 31 Oct and 6 Nov
    for day in [dt.date(year, 10, 31) + dt.timedelta(days=i) for i in range(7)]:
        if day.weekday() == 5:
            hol[day] = "All Saints' Day"
    return hol


@dataclass
class TimeBase:
    start: dt.date
    n_days: int
    tz: str
    hours_utc: pd.DatetimeIndex
    hour_local: np.ndarray       # 0..23
    day_idx: np.ndarray          # 0..n_days-1 per hour
    dates: list                  # local dates
    weekday_d: np.ndarray        # per day 0=Mon
    month_d: np.ndarray          # per day 1..12
    isoweek_d: np.ndarray
    holiday_d: np.ndarray        # bool per day
    holiday_name_d: list
    business_d: np.ndarray       # operator working day (Mon-Fri, not holiday)
    day_start_h: np.ndarray      # first hour index of each local day
    month_keys: list             # 'YYYY-MM' per hour-unique month order

    @property
    def n_hours(self) -> int:
        return len(self.hours_utc)

    def month_key_d(self) -> np.ndarray:
        return np.array([f"{d.year:04d}-{d.month:02d}" for d in self.dates])

    def hour_of(self, date: dt.date, hour: int) -> int:
        di = (date - self.start).days
        di = min(max(di, 0), self.n_days - 1)
        return int(min(self.day_start_h[di] + hour, self.n_hours - 1))

    def day_of_date(self, date) -> int:
        if isinstance(date, str):
            date = dt.date.fromisoformat(date)
        return (date - self.start).days


def build_timebase(start: str, n_days: int, tz: str = "Europe/Helsinki") -> TimeBase:
    start_d = dt.date.fromisoformat(start)
    end_d = start_d + dt.timedelta(days=n_days)
    t0 = pd.Timestamp(start_d).tz_localize(tz).tz_convert("UTC")
    t1 = pd.Timestamp(end_d).tz_localize(tz).tz_convert("UTC")
    hours = pd.date_range(t0, t1, freq="h", inclusive="left")
    local = hours.tz_convert(tz)
    hour_local = local.hour.to_numpy().astype(np.int8)
    local_dates = local.date
    dates = [start_d + dt.timedelta(days=i) for i in range(n_days)]
    date_to_idx = {d: i for i, d in enumerate(dates)}
    day_idx = np.fromiter((date_to_idx[d] for d in local_dates), dtype=np.int32, count=len(hours))
    hol = {}
    for y in range(start_d.year, end_d.year + 1):
        hol.update(finnish_holidays(y))
    weekday_d = np.array([d.weekday() for d in dates], dtype=np.int8)
    month_d = np.array([d.month for d in dates], dtype=np.int8)
    isoweek_d = np.array([d.isocalendar()[1] for d in dates], dtype=np.int16)
    holiday_d = np.array([d in hol for d in dates])
    holiday_name_d = [hol.get(d) for d in dates]
    business_d = (weekday_d < 5) & ~holiday_d
    day_start_h = np.searchsorted(day_idx, np.arange(n_days), side="left").astype(np.int64)
    month_keys = sorted({f"{d.year:04d}-{d.month:02d}" for d in dates})
    return TimeBase(start_d, n_days, tz, hours, hour_local, day_idx, dates, weekday_d, month_d,
                    isoweek_d, holiday_d, holiday_name_d, business_d, day_start_h, month_keys)
