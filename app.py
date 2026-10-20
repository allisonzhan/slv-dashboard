"""Streamlit entry point: streamlit run app.py"""

import streamlit as st

from slv_dashboard import config

st.set_page_config(page_title="SLV Dashboard", layout="wide")

st.title("Silver Dashboard")
st.caption("COINS metals division")

if not config.FRED_API_KEY:
    st.warning("FRED_API_KEY is not set. Copy .env.example to .env and add your key.")

st.info("Panels arrive in Phase 3 once the data loaders are in place.")

PLANNED_PANELS = [
    "Silver price and gold/silver ratio",
    "CFTC managed-money positioning",
    "COMEX registered vs. eligible stocks",
    "ETF holdings",
    "Real yields and the dollar",
    "Current regime and driver sensitivities",
]
st.markdown("\n".join(f"- {p}" for p in PLANNED_PANELS))
