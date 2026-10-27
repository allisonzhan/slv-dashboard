---
name: weekly-brief
description: Produce the COINS silver division's weekly meeting brief. Refreshes all data, runs the models and analog engine, exports the one-page brief and chart pack, then researches the week's relevant macro and silver news and writes the bottom line, news and talking points. Use when asked for the weekly brief, the silver update, or the meeting notes.
---

# Weekly silver brief

The full writing instructions are in `prompts/weekly_brief.md`. Read that file first; it is the same prompt the
future API agent (`slv_dashboard/agent.py`) will use.

## Steps

1. **Refresh the data and models.** Run these from the repo root with the project venv
   (`.venv/Scripts/python.exe` on Windows, `.venv/bin/python` elsewhere):
   ```
   python -m slv_dashboard.refresh
   python -m slv_dashboard.models.report
   python -m slv_dashboard.analogs.report
   python -m slv_dashboard.export          # SLV by default; add --instrument gld|iau|silver|gold for another
   ```
   `analogs.report` takes a few minutes (walk-forward backtest); run it in the background if your tools allow.
   If `data/cache/analog_backtest_slv_13w.csv` was already written today, you can skip it.
   A source that prints `FAILED` is not fatal. Mention it in your reply.

2. **Read the inputs.** Read `reports/<date>/snapshot.json` and `reports/<date>/brief.md`, plus the top ~40 rows
   of `data/cache/news.csv`.

3. **Research the news.**
   - Pick the headlines that plausibly moved silver's drivers this week. Typical ones: the Fed decision or
     Fed-speak, CPI, payrolls, dollar moves, gold flows, geopolitics, China data, solar demand, mine
     disruptions, ETF and COMEX flows.
   - Use web search to confirm facts and get the actual numbers, e.g. the rate decision, the CPI print vs.
     consensus, the tariff details.
   - Look beyond the cached headlines if something big is missing, e.g. a Silver Institute report or an exchange
     margin change.

4. **Write the AGENT blocks.** Edit `brief.md` by replacing the content between `<!-- AGENT:bottom_line -->`,
   `<!-- AGENT:news -->` and `<!-- AGENT:talking_points -->` and their `<!-- /AGENT -->` closers. Keep the markers
   and don't touch anything outside them.

5. **Re-render** with `python -m slv_dashboard.export --html`.

6. **Reply** with:
   - the path to `brief.html` (print it to PDF from a browser for the meeting);
   - the bottom line;
   - any data source that failed or looks stale.
