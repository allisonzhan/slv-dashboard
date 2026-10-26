"""Headlines from free RSS feeds, tagged by the silver driver they bear on.

No LLM here: headlines are keyword-tagged into driver buckets and given a
relevance score, so the weekly-brief agent (Claude Code for now) starts
from a short, sorted list instead of the open web. The agent then decides
what actually matters and why.

Feeds: Google News searches (one per driver, last 7 days), Fed press
releases, and FXStreet / Investing.com commodity news. Headlines only; the
agent opens articles it needs.
"""

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import pandas as pd
import requests

from slv_dashboard.config import HTTP_HEADERS, HTTP_TIMEOUT
from slv_dashboard.data import cache

NAME = "news"
LOOKBACK_DAYS = 8


def _google(q: str) -> str:
    return f"https://news.google.com/rss/search?q={quote_plus(q + ' when:7d')}&hl=en-US&gl=US&ceid=US:en"


FEEDS = {
    "google:silver": _google("silver price"),
    "google:silver_supply": _google("silver mine OR silver supply OR silver deficit"),
    "google:silver_market": _google("COMEX silver OR SLV OR silver ETF OR LBMA silver"),
    "google:fed": _google("Federal Reserve rates inflation"),
    "google:gold": _google("gold price"),
    "google:solar": _google("solar panel silver demand"),
    "google:china": _google("China manufacturing PMI industrial"),
    "fed": "https://www.federalreserve.gov/feeds/press_all.xml",
    "fxstreet": "https://www.fxstreet.com/rss/news",
    "investing": "https://www.investing.com/rss/news_11.rss",
}

# Driver bucket -> keywords. Whole words by default; a trailing * matches a prefix.
BUCKETS = {
    "fed_rates": ["fed", "fomc", "powell", "federal reserve", "rate cut*", "rate hike*", "interest rate*",
                  "treasur*", "yield*", "inflation", "cpi", "pce", "payroll*", "jobs report", "unemployment"],
    "dollar": ["dollar", "dxy", "greenback", "yuan", "yen", "currenc*"],
    "geopolitics": ["war", "wars", "sanction*", "tariff*", "iran*", "russia*", "ukrain*", "israel*", "missile*",
                    "election*", "safe haven", "safe-haven", "geopolit*"],
    "china_industrial": ["china", "chinese", "pmi", "manufactur*", "industrial", "copper", "electronics", "ev",
                         "evs"],
    "solar": ["solar", "photovoltaic*", "pv", "panel*"],
    "supply_mines": ["mine", "mines", "mining", "miner*", "production", "output", "strike*", "peru*", "mexic*",
                     "fresnillo", "recycl*", "deficit*", "silver institute", "smelter*"],
    "flows_market": ["etf*", "slv", "comex", "inventor*", "vault*", "lbma", "lease*", "squeeze*", "backwardation",
                     "cftc", "positioning", "hedge fund*", "deliver*"],
}
SILVER_WORDS = ["silver", "xag*"]
METAL_WORDS = ["gold", "precious", "bullion", "xau*", "metal*"]


def _pattern(words: list[str]) -> re.Pattern:
    parts = [re.escape(w[:-1]) if w.endswith("*") else re.escape(w) + r"\b" for w in words]
    return re.compile(r"\b(?:" + "|".join(parts) + ")")


_BUCKET_RE = {b: _pattern(ws) for b, ws in BUCKETS.items()}
_SILVER_RE, _METAL_RE = _pattern(SILVER_WORDS), _pattern(METAL_WORDS)


def tag(title: str) -> dict:
    """Driver buckets a headline touches and a relevance score for silver."""
    t = title.lower()
    buckets = [b for b, rx in _BUCKET_RE.items() if rx.search(t)]
    silver = bool(_SILVER_RE.search(t))
    metal = bool(_METAL_RE.search(t))
    score = 3 * silver + metal + len(buckets)
    return {"buckets": ",".join(buckets), "silver": silver, "relevance": score}


def parse_rss(xml_text: str, feed: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        pub = item.findtext("pubDate")
        try:
            when = parsedate_to_datetime(pub).astimezone(tz=None).replace(tzinfo=None) if pub else pd.NaT
        except (TypeError, ValueError):
            when = pd.NaT
        source = item.findtext("source") or feed
        # Google News titles end with " - Publisher"; keep the publisher in its own column
        m = re.match(r"^(.*) - ([^-]+)$", title)
        if feed.startswith("google:") and m:
            title, source = m.group(1).strip(), m.group(2).strip()
        out.append({"published": when, "title": title, "source": source, "link": item.findtext("link") or "",
                    "feed": feed})
    return out


def fetch() -> pd.DataFrame:
    rows = []
    for feed, url in FEEDS.items():
        try:
            resp = requests.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            rows += parse_rss(resp.text, feed)
        except (requests.RequestException, ET.ParseError):
            continue  # one dead feed shouldn't sink the rest
    return build(rows)


def build(rows: list[dict], now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Tag, keep the last LOOKBACK_DAYS, drop near-duplicate titles, sort by relevance then recency."""
    if not rows:
        return pd.DataFrame(columns=["published", "title", "source", "link", "feed", "buckets", "silver", "relevance"])
    df = pd.DataFrame(rows)
    df["published"] = pd.to_datetime(df["published"])
    now = now or pd.Timestamp.now()
    df = df[df["published"].isna() | (df["published"] >= now - pd.Timedelta(days=LOOKBACK_DAYS))]
    df = df.join(pd.DataFrame([tag(t) for t in df["title"]], index=df.index))
    key = df["title"].str.lower().str.replace(r"[^a-z0-9 ]", "", regex=True).str[:60]
    df = df[~key.duplicated()]
    df = df[df["relevance"] > 0]
    return df.sort_values(["relevance", "published"], ascending=False).reset_index(drop=True)


def refresh() -> pd.DataFrame:
    df = fetch()
    cache.save_table(NAME, df)
    return df


def top_by_bucket(df: pd.DataFrame, per_bucket: int = 3) -> dict[str, list[dict]]:
    out = {}
    for b in BUCKETS:
        hits = df[df["buckets"].fillna("").str.split(",").apply(lambda xs: b in xs)].head(per_bucket)
        out[b] = [{"title": r["title"], "source": r["source"], "published": str(r["published"])[:16],
                   "link": r["link"]} for _, r in hits.iterrows()]
    return out
