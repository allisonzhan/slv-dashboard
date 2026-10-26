"""Macro catalysts: FOMC decisions, payrolls and CPI, plus anything added by hand.

FOMC dates are the decision day (second day of the meeting), from the Fed's
published schedule; 2027 dates were announced as tentative. Extend the list
each year from https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm

Payrolls (first Friday) and CPI (around the 12th) are estimates: BLS moves
them for holidays. Put exact dates, or anything else that matters for silver
(Silver Institute reports, China data, tariff deadlines), in
data/imports/calendar.csv with columns date,event and they are merged in.
"""

from datetime import date, timedelta

import pandas as pd

from slv_dashboard.config import IMPORTS_DIR

FOMC_DECISIONS = [
    "2019-01-30", "2019-03-20", "2019-05-01", "2019-06-19", "2019-07-31", "2019-09-18", "2019-10-30", "2019-12-11",
    "2020-01-29", "2020-03-03", "2020-03-15", "2020-04-29", "2020-06-10", "2020-07-29", "2020-09-16", "2020-11-05",
    "2020-12-16",
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16", "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14", "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
    "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09", "2027-07-28", "2027-09-15", "2027-10-27", "2027-12-08",
]

MANUAL_FILE = IMPORTS_DIR / "calendar.csv"


def fomc_dates() -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(FOMC_DECISIONS))


def _first_friday(y: int, m: int) -> date:
    d = date(y, m, 1)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def _estimated(start: date, end: date) -> list[dict]:
    out = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        out.append({"date": _first_friday(y, m), "event": "US payrolls (est., first Friday)", "kind": "data"})
        cpi = date(y, m, 12)
        while cpi.weekday() >= 5:
            cpi += timedelta(days=1)
        out.append({"date": cpi, "event": "US CPI (est.)", "kind": "data"})
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def upcoming(today: date | None = None, days: int = 21) -> pd.DataFrame:
    """Events in the next ``days`` days, soonest first."""
    today = today or date.today()
    end = today + timedelta(days=days)
    rows = [{"date": d.date(), "event": "FOMC decision (2pm ET, press conference 2:30pm)", "kind": "fed"}
            for d in fomc_dates() if today <= d.date() <= end]
    rows += [r for r in _estimated(today, end) if today <= r["date"] <= end]
    if MANUAL_FILE.exists():
        manual = pd.read_csv(MANUAL_FILE, parse_dates=["date"])
        for _, r in manual.iterrows():
            if today <= r["date"].date() <= end:
                rows.append({"date": r["date"].date(), "event": r["event"], "kind": "manual"})
    df = pd.DataFrame(rows, columns=["date", "event", "kind"])
    return df.sort_values("date").reset_index(drop=True)


def fomc_week_mask(index: pd.DatetimeIndex) -> pd.Series:
    """True for weekly rows whose Friday-ending week contains an FOMC decision."""
    weeks = set(fomc_dates().to_period("W-FRI"))
    return pd.Series([p in weeks for p in index.to_period("W-FRI")], index=index)
