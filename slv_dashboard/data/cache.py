"""CSV cache for downloaded series, one file per dataset."""

import pandas as pd

from slv_dashboard.config import CACHE_DIR


def path(name: str):
    return CACHE_DIR / f"{name}.csv"


def save(name: str, df: pd.DataFrame) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.sort_index().to_csv(path(name), index_label="date")


def load(name: str) -> pd.DataFrame | None:
    p = path(name)
    if not p.exists():
        return None
    return pd.read_csv(p, index_col="date", parse_dates=["date"])


def append(name: str, new: pd.DataFrame) -> pd.DataFrame:
    """Merge new rows into the cached file; new values win on duplicate dates."""
    old = load(name)
    combined = new if old is None else pd.concat([old, new])
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    save(name, combined)
    return combined
