# Silver playbook

How silver trades, what professional metals desks watch, and where each item lives in the dashboard. Read it
once end to end, then use the weekly checklist at the bottom.

---

## 1. What silver is (to the market)

Silver is two assets in one:

- **A monetary metal.** It trades as a high-beta version of gold. Over 2010–2026 weekly data, silver moves about
  1.3–1.5x gold's percentage move (dashboard: *Macro → sensitivities*, `WITH_GOLD` spec). When gold rallies on
  falling real yields, a weaker dollar or safe-haven demand, silver usually rallies harder. It also falls harder.
- **An industrial input.** Roughly half of demand is industrial: electronics, solar photovoltaics, brazing,
  EVs. So silver also responds to the global manufacturing cycle, China and copper.

Which half dominates changes over time. The *monetary vs. industrial* regime panel measures it: how much of
silver's weekly movement copper explains relative to gold. When silver is "industrial", copper and China
headlines matter more. When it is "monetary", the Fed and gold matter most.

**Why silver is volatile:**
- The market is small: annual mine supply is roughly 800–850 Moz, a fraction of gold's value.
- Most supply is a **by-product** of lead, zinc, copper and gold mining (about 70%), so producers can't respond
  quickly to price.
- Investment flows (ETFs, coins and bars, futures specs) can swamp the physical balance in the short run.

**The structural backdrop (2026):**
- The Silver Institute expects a sixth straight market deficit (about 46 Moz in its April 2026 survey).
- Industrial demand is forecast at a four-year low of about 650 Moz as high prices push solar makers to thrift
  silver.
- Investment demand is what's carrying the market.
- Deficits draw down above-ground stocks over years. They don't set next month's price, but they shape how
  violent squeezes get (October 2025).

## 2. The drivers, in order of how much they usually matter

| Driver | Mechanism | Usual sign for silver | Dashboard |
|---|---|---|---|
| **Real yields** (10Y TIPS) | Silver pays no yield. Higher real yields raise the opportunity cost of holding it | Rising real yields → bearish | Macro → real yield; sensitivities |
| **Fed path** (2Y yield, FOMC) | Drives real yields and the dollar; expectations move before decisions | Hawkish surprise → bearish | Macro → 2Y; catalysts; FOMC-week setup |
| **US dollar** | Metals are priced in USD; a stronger dollar makes them dearer abroad | Stronger dollar → bearish | Macro → broad dollar |
| **Gold** | Silver's monetary anchor; central-bank and safe-haven demand flows through gold | Gold up → silver up more | Gold/silver ratio; Valuation |
| **Risk and liquidity** (VIX, equities) | In a panic, silver sells off with risk assets first (2008, March 2020); in slow-burn stress it trades with gold | Liquidation → bearish short term | VIX in What changed; Markov "stressed" regime |
| **Industrial cycle** (copper, China PMI) | Electronics and solar demand; China is the marginal buyer and fabricator | Stronger manufacturing → bullish | Copper; regime panel; China news bucket |
| **Solar** | Largest single growth use; high prices accelerate thrifting | Strong installs → bullish; thrifting → bearish | Solar news bucket |
| **Supply** | Mine disruptions (Mexico and Peru are the biggest producers), by-product economics | Disruptions → bullish | Supply news bucket |
| **Physical tightness** | Lease rates, backwardation, COMEX registered stocks, LBMA vault levels | Tight → bullish, squeeze risk | Supply & Flows → curve, implied lease rate |
| **Positioning** (CFTC managed money) | Specs chase trends; extremes become fuel for reversals | Crowded short → bullish contrarian | Positioning; crowded-short and crowded-long setups |
| **ETF flows** (SLV ounces) | Western investment demand | Inflows → bullish | Supply & Flows → SLV ounces |

**Geopolitics** usually reaches silver through gold (safe-haven bids) and through oil, inflation and the Fed
(e.g. an oil shock that makes the Fed more hawkish can be *bearish*). Tariffs can also hit silver directly, by
moving metal between COMEX and London and disrupting the physical market.

## 3. Market structure in one page

- **Venues.**
  - **COMEX (CME)** is the US futures market. The 5,000 oz `SI` contract trades in active months Mar, May, Jul,
    Sep and Dec.
  - **London (LBMA)** is the global spot and OTC hub.
  - **Shanghai (SGE/SHFE)** is the Chinese market. Its premium over London shows Chinese demand and import
    tightness.
- **Contango is normal.** A later future trades above the front by roughly the cost of financing the metal.
  When the spread narrows below the funding cost, or flips to **backwardation**, someone is paying up for metal
  now. The **implied lease rate** (funding rate minus the spread-implied financing rate) captures this. It spiked
  in the October 2025 squeeze.
- **COMEX stocks.** *Registered* ounces have a warrant and can be delivered against futures. *Eligible* ounces
  are in the vault but not warranted. Falling registered stocks against open interest is a delivery-squeeze
  warning.
- **COT report.** It splits futures positions into producers/merchants, swap dealers, managed money (hedge
  funds and CTAs) and others.
  - Managed money is the trend-following "hot money". Its *extremes* are the signal, not its level.
  - Positions are as of Tuesday and released Friday; the dashboard lags them so no model sees them early.
- **Ways to express a view:**
  - **SLV:** simple; it tracks spot minus fees.
  - **SI futures:** leverage and exact exposure, but they need rolling and margin.
  - **SLV options:** defined risk; you pay for implied vol.
  - **Miners (SIL):** leveraged to the silver price but carry equity and operational risk.
  - **The gold/silver ratio:** a relative-value trade with no outright direction.

## 4. How a desk actually works the week

- **Daily:** check overnight moves in gold, the dollar, yields and Shanghai. Watch for scheduled data, Fed
  speakers, curve spreads and lease rates, and ETF flows.
- **Weekly:**
  - Friday's COT release.
  - The weekly change in each driver vs. its usual range.
  - Whether the regime shifted (monetary ↔ industrial, calm ↔ stressed).
  - What setups are live, and how they have played out before.
  - Next week's catalysts.
- **Monthly:** re-check the thesis against valuation (rich or cheap vs. drivers), the supply/demand narrative,
  and positioning. Re-underwrite or exit trades.
- **The discipline that separates good traders from the rest:**
  - Every view has a base rate, a catalyst, an invalidation level and a size that survives being wrong.
  - Good desks write these down before the trade.

## 5. Using historical analogs without fooling yourself

The *Technicals & Analogs* tab finds past weeks that looked like this one and shows what happened next. It is
the hardest data to assemble by hand, so it is valuable. It is also easy to misuse.

- **Always compare against the base rate.** "Up 65% of the time" means little if silver rose in 54% of all
  13-week windows anyway. The edge is the difference.
- **Count independent episodes, not weeks.** The engine de-clusters, so one analog per 8 weeks. Twenty analogs
  are still only a handful of distinct regimes.
- **Respect the p-value.** Above about 0.1, the result could easily be chance.
- **Check the walk-forward track record.** It reruns the engine every week since 2010 using only what was known
  then. As of October 2026 it shows **no reliable directional edge** at 4 or 13 weeks. Treat analog direction
  calls as one input, not a signal.
- **Where analogs earn their keep is ranges.**
  - The typical and worst-quartile drawdown (MAE) after similar setups is a defensible stop.
  - The favourable excursion (MFE) gives targets.
  - Forward realised vol tells you whether options are cheap.
- **Read the episodes.** An analog from the 2011 blow-off or the 2020 COVID flush tells a different story from
  a quiet 2017 week, even at the same score.

## 6. Pitch structure (monthly)

The Trade Builder tab and the `monthly-pitch` skill produce a draft with these sections:

1. **Thesis:** what the market is missing, and why now.
2. **Evidence:** the scorecard lenses, both agreeing and disagreeing.
3. **History:** analogs and setups, always against base rates and the track record.
4. **What's priced:** positioning, implied vs. realised vol, the curve.
5. **Vehicle:** SLV, futures, an options spread or a ratio pair, and why.
6. **Risk:** stop, invalidation triggers, catalysts in the window.
7. **Exit plan:** targets, a time stop, and what to do at each catalyst.

## 7. Weekly checklist (meeting prep, about 20 minutes with the agent)

1. Run the `weekly-brief` skill in Claude Code, or run the refresh and export by hand (see README).
2. **Weekly Brief tab:** what changed, alerts, analog read, live setups, catalysts.
3. **Macro tab:**
   - Did real yields, the 2Y or the dollar move more than usual?
   - Did the regime change?
4. **Positioning tab:** where managed money sits vs. history and which way it moved.
5. **Supply & Flows tab:** the curve (backwardation? lease rate?), SLV flows, COMEX stocks if imported.
6. **Valuation tab:** rich or cheap vs. drivers, and the gold/silver ratio vs. its 3-year range.
7. **Technicals & Analogs tab:** the fan chart, the closest episodes and the setup scanner. Note the track record.
8. **Present:**
   - the bottom line, three news items tied to drivers, three talking points;
   - the next catalyst and what would change the view.

## Glossary

- **Real yield:** the nominal yield minus expected inflation; the 10Y TIPS yield.
- **Breakeven:** the market's implied inflation; nominal minus real yield.
- **Gold/silver ratio (GSR):** ounces of silver per ounce of gold. High means silver is cheap relative to gold.
- **Managed money:** hedge funds and CTAs in the COT report.
- **Contango / backwardation:** later futures above / below the front.
- **Lease rate:** the cost of borrowing physical silver. High means metal is scarce now.
- **MAE / MFE:** maximum adverse / favourable excursion, the worst and best move inside a holding period.
- **Base rate:** how often something happens unconditionally, the yardstick for any "edge".
- **Walk-forward:** testing a method on each date using only data available on that date.

_Sources for the 2026 market balance: Silver Institute / Metals Focus World Silver Survey (April 2026), as
reported by Kitco and Mining Weekly._
