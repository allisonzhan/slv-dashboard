"""COMEX silver warehouse stocks (registered / eligible) from CME's daily report.

CME blocks automated downloads, so this reads files you save by hand:
download https://www.cmegroup.com/delivery_reports/Silver_stocks.xls in your
browser and drop it into data/imports/ (any name starting with "Silver_stocks").
Each file is one day; history builds up in the cache as you import more.
"""

import re
from datetime import datetime

import pandas as pd

from slv_dashboard.config import IMPORTS_DIR
from slv_dashboard.data import cache

NAME = "comex_stocks"

ROW_LABELS = {
    "TOTAL REGISTERED": "registered_oz",
    "TOTAL ELIGIBLE": "eligible_oz",
    "COMBINED TOTAL": "total_oz",
}
_DATE_RE = re.compile(r"(Activity|Report) Date:\s*(\d{1,2}/\d{1,2}/\d{4})", re.IGNORECASE)


def parse(sheet: pd.DataFrame) -> pd.DataFrame:
    """Parse one report sheet (read with header=None) into a one-row frame."""
    dates: dict[str, datetime] = {}
    values: dict[str, float] = {}
    for _, row in sheet.iterrows():
        cells = [c for c in row.tolist() if pd.notna(c)]
        if not cells:
            continue
        for cell in cells:
            if isinstance(cell, str) and (m := _DATE_RE.search(cell)):
                dates[m[1].lower()] = datetime.strptime(m[2], "%m/%d/%Y")
        label = str(cells[0]).strip().upper()
        if label in ROW_LABELS:
            numbers = [c for c in cells[1:] if isinstance(c, (int, float))]
            if numbers:
                values[ROW_LABELS[label]] = float(numbers[-1])  # last column is "Total Today"
    # Activity date is the day the stocks refer to; fall back to report date
    date = dates.get("activity") or dates.get("report")
    if date is None or not values:
        raise ValueError("Could not find the date or registered/eligible totals in the CME file")
    return pd.DataFrame([values], index=pd.DatetimeIndex([date], name="date"))


def import_files() -> pd.DataFrame | None:
    files = sorted(IMPORTS_DIR.glob("Silver_stocks*.xls*"))
    if not files:
        return cache.load(NAME)
    frames = [parse(pd.read_excel(f, header=None)) for f in files]
    return cache.append(NAME, pd.concat(frames))


def refresh() -> pd.DataFrame | None:
    return import_files()
