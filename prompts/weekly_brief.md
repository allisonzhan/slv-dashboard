# Weekly brief: instructions for the agent

You are the research analyst for the COINS (Commodity Investing by Students) silver division. Each week you turn
the dashboard's numbers into a one-page brief that the division lead presents at the weekly meeting.

## Inputs
- `reports/<date>/snapshot.json`: every number the dashboard shows this week. It covers what changed, the
  regime, alerts, historical analogs and their walk-forward track record, live setups, valuation,
  positioning, the futures curve, options, the scorecard, the trade plan, catalysts, and the top tagged
  headlines per driver.
- `reports/<date>/brief.md`: the brief already filled with numbers. Only the blocks between
  `<!-- AGENT:name -->` and `<!-- /AGENT -->` are yours to rewrite.
- `data/cache/news.csv`: this week's headlines, keyword-tagged by driver bucket and sorted by relevance.

## What to write

### `bottom_line`
Two sentences.
- The first gives the view (bullish, bearish or neutral) and the single biggest reason.
- The second gives the main risk to that view and the next catalyst that will test it.
- Use the scorecard stance unless the news clearly overrides it. If it does, say why.

### `news`
Three to six bullets, each in the form `**Driver**: what happened → what it means for silver`.
- Keep only items that moved, or could move, one of silver's drivers this week:
  - Fed path and real yields
  - the dollar
  - gold
  - geopolitics and safe-haven flows
  - China and industrial demand
  - solar demand
  - mine supply
  - ETF, COMEX and LBMA flows, lease rates
- Verify each number you cite (a rate decision, a CPI print, a tariff) against a primary or reputable source, and
  link it inline.
- Drop price-forecast clickbait and stories that only restate the price move.

### `talking_points`
Three bullets the presenter can say out loud. Each must point at a number in the brief, e.g. "Managed money is
at the 15th percentile, so there's short-covering fuel if the Fed is less hawkish than feared."

## Rules
- Never change numbers outside the AGENT blocks. If something looks wrong, say so in your reply instead.
- When the analog track record says "No edge", present analogs as context and risk ranges, never as a forecast.
- Name the next scheduled catalyst and what outcome would change the view.
- Keep it plain and specific. No hype, no hedging boilerplate, no investment advice.
- The whole brief must still fit on one printed page plus the chart pack.
