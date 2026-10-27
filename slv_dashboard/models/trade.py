"""Trade builder: a scorecard across every lens, then a structured trade plan.

The scorecard scores six lenses from -2 (bearish) to +2 (bullish), each with
the reason in words, so a pitch can show its working:

  analogs      13-week analog edge vs. base rate, discounted when the
               walk-forward backtest shows no edge
  setups       named setups live this week (bullish vs. bearish reads)
  valuation    fair-value z-score (cheap is bullish)
  positioning  managed-money percentile (crowded short is bullish)
  macro        13-week change in real yields and the dollar (falling is bullish)
  curve        backwardation / lease-rate spike (tight metal is bullish);
               silver only, since the gold curve isn't tracked

The plan turns the stance into a vehicle, entry, stop, targets and size, in
the chosen instrument's price (SLV by default; see slv_dashboard/instruments.py).
Stops and targets come from the analogs' adverse/favourable excursions, so
they reflect how far the instrument actually moved in similar setups. This is
a decision aid for club pitches, not investment advice.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from slv_dashboard import instruments
from slv_dashboard.config import DEFAULT_INSTRUMENT

LENSES = ["analogs", "setups", "valuation", "positioning", "macro", "curve"]


@dataclass
class Score:
    lens: str
    score: int          # -2..+2
    reason: str


@dataclass
class Scorecard:
    scores: list[Score]

    @property
    def total(self) -> int:
        return sum(s.score for s in self.scores)

    @property
    def stance(self) -> str:
        if self.total >= 3:
            return "bullish"
        if self.total <= -3:
            return "bearish"
        return "neutral"

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame([{"Lens": s.lens.title(), "Score": s.score, "Why": s.reason} for s in self.scores])


def _clip(x: float) -> int:
    return int(np.clip(np.round(x), -2, 2))


def score_analogs(outcomes: pd.DataFrame | None, backtest_has_edge: bool) -> Score:
    if outcomes is None or 13 not in outcomes.index:
        return Score("analogs", 0, "No analog read")
    o = outcomes.loc[13]
    raw = 0
    if o["p_value"] <= 0.2:
        raw = 2 if abs(o["edge_median"]) >= 0.05 else 1
        raw *= int(np.sign(o["edge_median"]))
    if not backtest_has_edge:
        raw = int(np.sign(raw)) if raw else 0   # cap at ±1 when the track record shows no edge
    why = (f"13w analog median {o['median']:+.1%} vs. base {o['base_median']:+.1%}, up {o['hit_rate']:.0%} "
           f"(p {o['p_value']:.2f})")
    if not backtest_has_edge:
        why += "; capped because the walk-forward backtest shows no reliable edge"
    return Score("analogs", raw, why)


def score_setups(scan: pd.DataFrame | None) -> Score:
    if scan is None or scan.empty:
        return Score("setups", 0, "No setup scan")
    live = scan[scan["live"] & (scan["horizon_weeks"] == 13)]
    if live.empty:
        return Score("setups", 0, "No named setups live")
    bull = live[live["view"] == "bullish"]["setup"].tolist()
    bear = live[live["view"] == "bearish"]["setup"].tolist()
    other = live[~live["view"].isin(["bullish", "bearish"])]["setup"].tolist()
    parts = ([f"bullish: {', '.join(bull)}"] if bull else []) + ([f"bearish: {', '.join(bear)}"] if bear else []) + \
        ([f"other: {', '.join(other)}"] if other else [])
    return Score("setups", _clip(len(bull) - len(bear)), "; ".join(parts))


def score_valuation(fv: pd.DataFrame | None) -> Score:
    if fv is None or fv.empty:
        return Score("valuation", 0, "No fair-value model")
    z = float(fv["z"].iloc[-1])
    return Score("valuation", _clip(-z), f"{fv['residual_pct'].iloc[-1]:+.0%} vs. driver fair value (z {z:+.1f})")


def score_positioning(mm_pctile: float | None) -> Score:
    if mm_pctile is None or pd.isna(mm_pctile):
        return Score("positioning", 0, "No COT data")
    s = 2 if mm_pctile < 0.1 else 1 if mm_pctile < 0.3 else -2 if mm_pctile > 0.9 else -1 if mm_pctile > 0.7 else 0
    crowd = "short-covering fuel" if s > 0 else "crowded long, liquidation risk" if s < 0 else "neutral"
    return Score("positioning", s, f"Managed money at the {mm_pctile:.0%} percentile of history: {crowd}")


def score_macro(ry_chg_13w: float | None, usd_ret_13w: float | None) -> Score:
    s, parts = 0.0, []
    if ry_chg_13w is not None and pd.notna(ry_chg_13w):
        s += -np.clip(ry_chg_13w / 0.25, -1, 1)          # 25bp move = one point
        parts.append(f"real yields {ry_chg_13w * 100:+.0f}bp over 13w")
    if usd_ret_13w is not None and pd.notna(usd_ret_13w):
        s += -np.clip(usd_ret_13w / 0.03, -1, 1)         # 3% dollar move = one point
        parts.append(f"dollar {usd_ret_13w:+.1%}")
    return Score("macro", _clip(s), ", ".join(parts) or "No macro data")


def score_curve(curve: pd.DataFrame | None) -> Score:
    if curve is None or curve.empty:
        return Score("curve", 0, "No futures curve data")
    last = curve.dropna(subset=["front", "next"]).iloc[-1]
    lease = last.get("implied_lease_pct", np.nan)
    if bool(last["backwardation"]):
        return Score("curve", 2, "Backwardation: near-term metal scarce")
    if pd.notna(lease) and lease >= 3:
        return Score("curve", 1, f"Implied lease rate {lease:.1f}%: physical tightening")
    return Score("curve", 0, f"Normal contango (implied lease {lease:+.1f}%)" if pd.notna(lease) else "Normal contango")


def build_scorecard(*, outcomes=None, backtest_has_edge=False, scan=None, fv=None, features: pd.Series | None = None,
                    curve=None, metal: str = "silver") -> Scorecard:
    f = features if features is not None else pd.Series(dtype=float)
    if metal != "silver":
        curve_score = Score("curve", 0, "Not tracked for gold (silver futures curve only)")
    else:
        curve_score = score_curve(curve)
    return Scorecard([
        score_analogs(outcomes, backtest_has_edge),
        score_setups(scan),
        score_valuation(fv),
        score_positioning(f.get("mm_pctile")),
        score_macro(f.get("ry_chg_13w"), f.get("usd_ret_13w")),
        curve_score,
    ])


@dataclass
class TradePlan:
    stance: str
    instrument: str
    rationale: str
    entry: float
    stop: float
    targets: list[float]
    horizon_weeks: int
    risk_pct_of_book: float          # percent, e.g. 1.0 = 1%
    position_pct_of_book: float      # fraction, e.g. 0.075 = 7.5%
    reward_risk: float
    invalidation: list[str] = field(default_factory=list)


def suggest_instrument(stance: str, iv: float | None, realised_vol: float | None, gsr_pctile: float | None,
                       instrument: str = DEFAULT_INSTRUMENT) -> tuple[str, str]:
    """Pick the vehicle from the view and whether options are cheap or rich vs. what analogs realised.

    Names follow the chosen instrument: its own ETF (e.g. IAU) or the metal's
    main ETF for a futures pick, the metal's futures contract, and the ETF
    whose options are liquid (SLV for silver, GLD for gold).
    """
    inst = instruments.get(instrument)
    etf = instrument.upper() if inst.kind == "etf" else instruments.VEHICLES[inst.metal]["etf"]
    fut = instruments.VEHICLES[inst.metal]["futures"]
    opt = inst.options
    iv_note = ""
    cheap = rich = False
    if iv is not None and realised_vol is not None and pd.notna(iv) and pd.notna(realised_vol):
        cheap, rich = iv < realised_vol * 0.95, iv > realised_vol * 1.05
        iv_note = f" {opt} IV {iv:.0%} vs. analog realised {realised_vol:.0%}."
    if stance == "bullish":
        if cheap:
            return (f"{opt} call spread (~30-60 days)",
                    f"Options are cheap vs. how far {inst.metal} moved in similar setups." + iv_note)
        if rich:
            return f"Long {etf} (or {fut} futures) with a hard stop", "Options are rich, so own the metal and use a stop." + iv_note
        return f"Long {etf} with a stop, or a call spread", "No strong options edge either way." + iv_note
    if stance == "bearish":
        if cheap:
            return f"{opt} put spread (~30-60 days)", "Defined-risk downside; options are cheap." + iv_note
        if rich:
            return f"Short {fut} futures or {opt} bear call spread", "Options are rich: sell premium against the view." + iv_note
        return f"Short {etf} with a stop, or a put spread", "No strong options edge either way." + iv_note
    if gsr_pctile is not None and pd.notna(gsr_pctile) and (gsr_pctile > 0.9 or gsr_pctile < 0.1):
        side = "long silver / short gold" if gsr_pctile > 0.9 else "long gold / short silver"
        return f"Relative value: {side} (gold/silver ratio pair)", (
            f"No directional edge, but the ratio is at its {gsr_pctile:.0%} percentile of the last 3 years.")
    return "No trade: wait for a clearer setup", "The lenses disagree; the best pitch may be the setup to watch for."


def plan(scorecard: Scorecard, outcomes: pd.DataFrame | None, price: float, *, horizon_weeks: int = 13,
         risk_pct: float = 1.0, iv: float | None = None, gsr_pctile: float | None = None,
         instrument: str = DEFAULT_INSTRUMENT) -> TradePlan:
    """Entry, stop, targets and size for the scorecard's stance.

    Long: stop at the analogs' worst-quartile adverse move, targets at the
    median and 75th-percentile favourable move. Short mirrors it. Position
    size risks ``risk_pct`` of the book if the stop is hit.
    """
    stance = scorecard.stance
    o = outcomes.loc[horizon_weeks] if outcomes is not None and horizon_weeks in outcomes.index else None
    realised = float(o["fwd_vol_median"]) if o is not None else None
    vehicle, rationale = suggest_instrument(stance, iv, realised, gsr_pctile, instrument)
    if o is None or stance == "neutral":
        return TradePlan(stance, vehicle, rationale, price, np.nan, [], horizon_weeks, risk_pct, 0.0, np.nan,
                         invalidation_triggers(scorecard))
    if stance == "bullish":
        stop = price * (1 + min(o["mae_q25"], -0.03))
        targets = [price * (1 + o["mfe_median"]), price * (1 + o["mfe_q75"])]
    else:
        # For a short, the adverse move is up (the analogs' MFE) and the favourable move is down (MAE)
        stop = price * (1 + max(o["mfe_q75"], 0.03))
        targets = [price * (1 + o["mae_median"]), price * (1 + o["mae_q25"])]
    stop_dist = abs(price - stop) / price
    reward = abs(targets[0] - price) / price
    return TradePlan(stance, vehicle, rationale, price, stop, targets, horizon_weeks, risk_pct,
                     position_pct_of_book=risk_pct / 100 / stop_dist if stop_dist > 0 else 0.0,
                     reward_risk=reward / stop_dist if stop_dist > 0 else np.nan,
                     invalidation=invalidation_triggers(scorecard))


def invalidation_triggers(scorecard: Scorecard) -> list[str]:
    """What would change the view, phrased for the pitch."""
    bull = scorecard.stance != "bearish"
    out = ["Stop level hit on a weekly close"]
    out.append("Real yields rise 25bp+ from here" if bull else "Real yields fall 25bp+ from here")
    out.append("Dollar breaks out higher (3%+ in a month)" if bull else "Dollar breaks down (3%+ in a month)")
    out.append("Managed money flips to the top 10% of history (crowded long)" if bull
               else "Managed money drops to the bottom 10% (crowded short)")
    return out


def pitch_markdown(sc: Scorecard, tp: TradePlan, *, as_of: pd.Timestamp, analog_lines: list[str],
                   catalysts: pd.DataFrame | None = None, backtest_verdict: str = "",
                   instrument: str = DEFAULT_INSTRUMENT) -> str:
    """Pre-filled monthly pitch skeleton; the narrative sections are left for the analyst (or the agent)."""
    def money(x):
        return "–" if pd.isna(x) else f"${x:,.2f}"

    lines = [
        f"# {instruments.get(instrument).label} trade pitch: {as_of:%B %Y}",
        "",
        f"**Stance:** {tp.stance.upper()} (scorecard {sc.total:+d} of ±12)  ",
        f"**Vehicle:** {tp.instrument}  ",
        f"**Horizon:** {tp.horizon_weeks} weeks",
        "",
        "## Thesis",
        "_Two or three sentences: what the market is missing and why now._",
        "",
        "## Scorecard",
        "| Lens | Score | Why |",
        "|---|---|---|",
        *[f"| {s.lens.title()} | {s.score:+d} | {s.reason} |" for s in sc.scores],
        "",
        "## Historical analogs",
        *[f"- {line}" for line in analog_lines],
    ]
    if backtest_verdict:
        lines.append(f"- Track record: {backtest_verdict}")
    lines += ["", "## Trade plan"]
    if tp.stance == "neutral":
        lines += [f"- {tp.rationale}"]
    else:
        lines += [
            f"- Entry: {money(tp.entry)}",
            f"- Stop: {money(tp.stop)} ({(tp.stop / tp.entry - 1):+.1%}, analogs' worst-quartile adverse move)",
            f"- Targets: " + ", ".join(f"{money(x)} ({x / tp.entry - 1:+.1%})" for x in tp.targets),
            f"- Reward/risk to first target: {tp.reward_risk:.1f}x",
            f"- Size: {tp.position_pct_of_book:.0%} of the book risks {tp.risk_pct_of_book:.1f}% at the stop",
            f"- Why this vehicle: {tp.rationale}",
        ]
    lines += ["", "## Catalysts"]
    if catalysts is not None and not catalysts.empty:
        lines += [f"- {r['date']:%b %d}: {r['event']}" for _, r in catalysts.iterrows()]
    else:
        lines.append("- _None scheduled in the window; add any you're watching._")
    lines += ["", "## What would make us wrong", *[f"- {x}" for x in tp.invalidation], "",
              "_Club research for educational purposes, not investment advice._"]
    return "\n".join(lines)
