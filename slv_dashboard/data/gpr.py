"""Geopolitical risk (GPR) index, daily, from Caldara and Iacoviello.

The index counts newspaper articles about geopolitical tensions (wars,
military threats, terrorism) in 10 major papers; 1985-2019 averages 100.
GPRD_ACT counts adverse events that happened, GPRD_THREAT counts threats and
warnings. The authors annotate the biggest spikes; those labels feed the
event catalogue (slv_dashboard/events.py).

The day-t reading is built from day-t newspapers, so the dataset shifts it
one day forward before joining prices (no look-ahead).

Cite: Caldara, Dario and Matteo Iacoviello (2022), "Measuring Geopolitical
Risk," American Economic Review 112(4).
"""

import io

import pandas as pd
import requests

from slv_dashboard.config import GPR_DAILY_URL, HTTP_HEADERS, HTTP_TIMEOUT
from slv_dashboard.data import cache

NAME = "gpr"
EVENTS_NAME = "gpr_events"
PUBLICATION_LAG = pd.Timedelta(days=1)

COLUMNS = {"GPRD": "gpr", "GPRD_ACT": "gpr_act", "GPRD_THREAT": "gpr_threat"}


def parse(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(daily index frame, annotated events) from the authors' spreadsheet."""
    df = raw.copy()
    df.index = pd.to_datetime(df["date"])
    df.index.name = "date"
    out = df[list(COLUMNS)].apply(pd.to_numeric, errors="coerce").rename(columns=COLUMNS).dropna(subset=["gpr"])
    ev = df.loc[df["event"].notna(), ["event"]].rename(columns={"event": "title"})
    return out.sort_index(), ev


def fetch() -> tuple[pd.DataFrame, pd.DataFrame]:
    resp = requests.get(GPR_DAILY_URL, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return parse(pd.read_excel(io.BytesIO(resp.content)))


def refresh() -> pd.DataFrame:
    df, ev = fetch()
    cache.save(NAME, df)
    cache.save(EVENTS_NAME, ev)
    return df
