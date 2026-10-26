# Monthly trade pitch: instructions for the agent

Once a month the silver division pitches one trade. You draft it from `reports/<date>/pitch.md`, which already
contains the scorecard, the analog evidence, the trade plan (vehicle, entry, stop, targets, size), the
catalysts and the invalidation list. Everything comes from `snapshot.json`.

## What a good pitch answers (in this order)
1. **Thesis**: what is the market missing, and why now? One idea, stated in two or three sentences.
2. **Evidence**: which lenses agree and which disagree? Use the scorecard and say why the dissenting lenses
   don't kill the trade.
3. **History**: what did silver do after setups like this? Use the analogs and live setups. Quote the base rate
   next to every number. If the walk-forward track record shows no edge, say so and use the analogs only for
   sizing the stop and target.
4. **What's priced**: positioning (COT percentile), implied vol vs. the analogs' realised vol, and the futures
   curve. A crowded trade needs a better reason.
5. **Vehicle**: why this instrument (SLV, SI futures, an SLV option spread, or a gold/silver ratio pair) rather than
   the others.
6. **Risk**: the stop, what invalidates the thesis before the stop is hit, and the catalysts inside the
   holding period.
7. **Exit plan**: targets, a time stop (the horizon), and what you'd do at each catalyst.

## Rules
- Keep the numbers from `pitch.md` unless you have a better-sourced one. If you change one, say why.
- If the scorecard is neutral, pitch the best conditional trade instead ("if X happens, we do Y") or the ratio
  pair. Don't force a direction.
- Check every macro claim against a current source and link it.
- End with the "not investment advice" line.
