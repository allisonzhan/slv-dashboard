"""Offline tests for the source parsers and dataset alignment."""

import pandas as pd
import pytest

from slv_dashboard.data import cache, cftc, comex, dataset, etf, fred


def test_fred_keyless_csv_drops_gaps():
    text = "observation_date,DFII10\n2026-01-02,1.90\n2026-01-05,.\n2026-01-06,1.95\n"
    s = fred.parse_keyless_csv(text)
    assert list(s) == [1.90, 1.95]
    assert s.index[0] == pd.Timestamp("2026-01-02")


def test_cftc_parse_computes_net_positioning():
    record = {
        "report_date_as_yyyy_mm_dd": "2026-10-13T00:00:00.000",
        "open_interest_all": "100000",
        "m_money_positions_long_all": "30000",
        "m_money_positions_short_all": "10000",
        "prod_merc_positions_long": "1", "prod_merc_positions_short": "2",
        "swap_positions_long_all": "3", "swap__positions_short_all": "4",
    }
    df = cftc.parse([record])
    row = df.loc["2026-10-13"]
    assert row["mm_net"] == 20000
    assert row["mm_net_pct_oi"] == pytest.approx(20.0)


def test_etf_parse_reads_ounces_and_date():
    html = ('...&quot;ounces&quot;:{&quot;visible&quot;:true,&quot;label&quot;:&quot;Ounces in Trust&quot;,'
            '&quot;formattedValue&quot;:&quot;497,650,755.40&quot;,&quot;sortOrder&quot;:49,'
            '&quot;formattedAsOfDate&quot;:&quot;Oct 19, 2026&quot;,&quot;name&quot;:&quot;ounces&quot;}...')
    df = etf.parse(html)
    assert df.index[0] == pd.Timestamp("2026-10-19")
    assert df["slv_ounces"].iloc[0] == pytest.approx(497_650_755.40)


def test_etf_parse_fails_loudly_on_layout_change():
    with pytest.raises(ValueError):
        etf.parse("<html>no data here</html>")


def test_comex_parse_synthetic_report():
    sheet = pd.DataFrame([
        ["COMMODITY EXCHANGE, INC.", None, None],
        ["Report Date: 10/17/2026", None, None],
        ["Activity Date: 10/16/2026", None, None],
        ["DEPOSITORY", "PREV TOTAL", "TOTAL TODAY"],
        ["TOTAL REGISTERED", 190_000_000.0, 191_000_000.0],
        ["TOTAL ELIGIBLE", 300_000_000.0, 299_000_000.0],
        ["COMBINED TOTAL", 490_000_000.0, 490_000_000.0],
    ])
    df = comex.parse(sheet)
    assert df.index[0] == pd.Timestamp("2026-10-16")  # activity date, not report date
    assert df["registered_oz"].iloc[0] == 191_000_000.0
    assert df["eligible_oz"].iloc[0] == 299_000_000.0


def test_cot_is_not_visible_before_release(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    days = pd.bdate_range("2026-10-12", "2026-10-23", name="date")  # Mon..Fri, two weeks
    cache.save("prices", pd.DataFrame({"silver": 50.0, "gold": 4000.0, "copper": 6.0}, index=days))
    tuesday = pd.Timestamp("2026-10-13")
    cache.save("cot", pd.DataFrame({"mm_net": [5000]}, index=pd.DatetimeIndex([tuesday], name="date")))

    df = dataset.build()
    assert df.loc[:"2026-10-15", "mm_net"].isna().all()   # Tue-Thu: not yet published
    assert df.loc["2026-10-16", "mm_net"] == 5000          # Friday release
    assert df["gold_silver_ratio"].iloc[0] == pytest.approx(80.0)
