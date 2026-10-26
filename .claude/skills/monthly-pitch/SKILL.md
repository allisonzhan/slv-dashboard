---
name: monthly-pitch
description: Draft the COINS silver division's monthly trade pitch from the Trade Builder (scorecard, analogs, trade plan, catalysts), researching the macro backdrop to write the thesis. Use when asked for the monthly pitch, a trade idea, or a pitch deck outline for silver.
---

# Monthly silver trade pitch

The pitch structure and rules are in `prompts/monthly_pitch.md`. Read that file first.

## Steps

1. **Make sure this week's numbers exist.**
   - If `reports/` has no folder dated within the last 3 days, run the data steps of the `weekly-brief` skill
     (refresh, models.report, analogs.report, export).
   - Otherwise run `python -m slv_dashboard.export` to regenerate `pitch.md` from the latest cache.

2. **Read the inputs.** Read `reports/<date>/pitch.md` and `reports/<date>/snapshot.json`: the scorecard, trade
   plan, analogs, backtest verdicts, options, curve and catalysts.

3. **Research the thesis.**
   - What is the market pricing for the Fed path, the dollar and gold?
   - What are the silver-specific stories: supply, solar thrifting, ETF/COMEX flows, lease rates?
   - Use web search for current consensus and the dated catalysts inside the trade's horizon.

4. **Write the pitch.**
   - Fill in the Thesis section of `pitch.md` and tighten the rest, following the seven questions in
     `prompts/monthly_pitch.md`.
   - Keep the numbers. If the scorecard is neutral, write the conditional trade or the ratio pair instead of
     forcing a direction.

5. **Reply** with:
   - the path to `pitch.md`;
   - the one-line trade (vehicle, entry, stop, targets, horizon);
   - the strongest counter-argument.
   - Offer to turn it into slides if the division wants a deck.
