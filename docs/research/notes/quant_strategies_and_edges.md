# Quantitative (non-LLM / LLM-assisted) trading strategies on prediction markets: documented edges, competition and capacity (as of 2026-11-16)

Scope note: covers Polymarket (international CLOB on Polygon, plus Polymarket US), Kalshi (CFTC-regulated DCM), and some cross-venue work. Fee and API mechanics, LLM forecasting benchmarks and legal issues are covered by other researchers. They appear here only where they decide whether a strategy is viable. "Verified" means peer-reviewed or working-paper evidence or full on-chain datasets. "Anecdote/claim" means self-reported, vendor or social-media figures.

---

## 1. Arbitrage: intra-market, combinatorial and cross-platform

### Takeaway
Arbitrage on Polymarket was real and large in 2024–25: about $40M realized from April 2024 to April 2025. Almost all of it came from simple within-market rebalancing, mostly multi-outcome "NegRisk" markets. "Combinatorial" arbitrage across logically linked markets yielded under $100K. A small number of bot-like accounts captured a large share. Since January 2026, taker fees, sub-second competition and non-atomic leg risk make pure intra-market arbitrage a poor fit for retail. Cross-platform Kalshi↔Polymarket gaps of about 2–4% do persist. They come from structural frictions: resolution-wording mismatch, capital transfer, fees and lockup. Those frictions are the risk you are being paid for, so these trades are not risk-free.

### Cited Findings
**Saguillo, Ghafouri, Kiffer & Suarez-Tangil, "Unravelling the Probabilistic Forest: Arbitrage in Prediction Markets" (arXiv 2508.03474, v1 Aug 5 2025; IMDEA lists an Oct 2025 date)**
- Dataset: Polymarket markets resolved 1 Apr 2024 – 1 Apr 2025. 17,218 conditions: 8,659 single-condition markets plus 1,578 multi-condition (NegRisk) markets containing 8,559 conditions. Built from on-chain order and bid data, about 86M bids analyzed — [arXiv HTML](https://arxiv.org/html/2508.03474)
- Headline: about $39.59M realized arbitrage profit, rounded to "$40M" in the abstract — [arXiv abstract](https://arxiv.org/abs/2508.03474); [arXiv HTML](https://arxiv.org/html/2508.03474)
- Breakdown by type — [arXiv HTML](https://arxiv.org/html/2508.03474):
  - Single-condition "market rebalancing" (YES+NO ≠ $1): about $5.90M from buying both sides below $1 and about $4.68M from selling above $1, for about $10.58M total.
  - Multi-condition NegRisk rebalancing (outcome prices not summing to 100%): buying NO about $17.31M, buying YES about $11.09M, selling YES about $0.61M. About $29.0M total, which is the bulk of all profit.
  - Combinatorial (cross-market logical dependencies): only about $95K across 4 market pairs.
  - The paper's components don't sum exactly to the headline.
- Frequency — [arXiv HTML](https://arxiv.org/html/2508.03474):
  - 7,051 of about 17.2K conditions had at least one rebalancing opportunity.
  - 662 of 1,578 NegRisk markets had opportunities, averaging about 100 per market.
  - Opportunities clustered in volatile and low-liquidity periods.
  - Sports had the most NegRisk opportunities and the largest exploited single-condition profits. Politics, especially the US election, held the most potential single-condition profit.
  - Only about 1% of estimated US-election single-condition opportunities were actually exploited.
- Who captured it — [arXiv HTML](https://arxiv.org/html/2508.03474):
  - The top account earned about $2.01M over 4,049 transactions.
  - The top 10 accounts earned about $8.18M, about 21% of the total.
  - Some accounts show bot-like bid volumes.
  - One account bought YES and NO for under $0.02 each and made $58,983 in one trade.
- LLM-assisted detection — [arXiv HTML](https://arxiv.org/html/2508.03474):
  - The authors used DeepSeek-R1-Distill-Qwen-32B to flag logically dependent markets.
  - Of 46,360 US-election market pairs, 1,576 were flagged dependent. After manual review, only about 13 met the strict combinatorial-arbitrage definition.
  - Failure modes included invalid JSON, reasoning loops and conflating related election metrics.
- Execution is non-atomic, so a failed leg leaves an unhedged position. The paper does not measure how fast opportunities close — [arXiv HTML](https://arxiv.org/html/2508.03474)

**Cross-platform (Kalshi ↔ Polymarket ↔ others)**
- Gebele & Matthes (TU Munich), "Semantic Non-Fungibility and Violations of the Law of One Price in Prediction Markets" (arXiv 2601.01706, Jan 5 2026) — [arXiv](https://arxiv.org/abs/2601.01706):
  - Human-validated alignment of more than 100,000 events across 10 venues, 2018–2025.
  - About 6% of events are listed on multiple platforms at once.
  - Semantically equivalent markets show persistent, execution-aware price deviations of about 2–4% on average, even in liquid settings.
  - The authors attribute these to structural frictions, not information disagreement. They show Kalshi and Polymarket Senate-control markets that look like the same proposition but cannot be verified as payoff-equivalent.
- Dune blog (May 2026), three 2026 FOMC decisions across Kalshi, Polymarket and CME FedWatch: a gap of about 20¢ persisted for a stretch and narrowed to about 1¢ by decision day. Small sample, illustrative only — [Dune](https://dune.com/blog/pricing-the-fed-kalshi-polymarket-cme-fedwatch)
- Resolution-mismatch examples (no verified dollar-loss case found):
  - Postponed games: per Totalis, Polymarket pays 50¢, Kalshi applies a "fair price" and HIP-4 uses the real result — [Totalis](https://www.totalis.trade/blogs/prediction-markets/prediction-market-arbitrage)
  - Deadlines: Kalshi cutoffs often fall in the morning ET, while Polymarket's usually run to 11:59 PM ET — [OddsShopper](https://www.oddsshopper.com/articles/prediction-markets/kalshi-vs-polymarket-settlement-rules)
  - Data revisions: e.g., the advance vs. second GDP estimate.
  - Unilateral resolution: e.g., Kalshi's Khamenei market — [PredictionMarketsWorld](https://predictionmarketsworld.com/en-us/prediction-market-arbitrage/)
  - When rules diverge, both legs can lose. NexusFi's example shows a "+7.8¢ locked" pair becoming a −90¢ loss if the two venues settle in opposite directions — [NexusFi](https://nexusfi.com/a/prediction-markets/arbitrage-prediction-markets)
- Capital transfer between venues takes hours to days, because Kalshi uses bank rails and Polymarket uses Polygon/USDC — [summary of cross-venue guides, see Gebele & Matthes context](https://arxiv.org/abs/2601.01706); [NexusFi](https://nexusfi.com/a/prediction-markets/arbitrage-prediction-markets)
- Related: Polymarket Bitcoin-threshold prices sit about 5–6pp above Binance option-implied probabilities. The persistent arbitrage is described as infrequent and small, which the summary attributes to capital-movement frictions (June 2026 study, seen only via summary) — [Emergent Mind summary](https://www.emergentmind.com/papers/2606.19517)

**Fee drag (relevant to all arbitrage)**
- Polymarket introduced taker fees on 15-minute crypto markets in January 2026. Fees are highest at 50% and fall toward the extremes, makers pay nothing, and the proceeds fund maker rebates. Polymarket stated the aim was to neutralize latency arbitrage — [The Block](https://www.theblock.co/post/384461/polymarket-adds-taker-fees-to-15-minute-crypto-markets-to-fund-liquidity-rebates); [Finance Magnates](https://www.financemagnates.com/cryptocurrency/polymarket-introduces-dynamic-fees-to-curb-latency-arbitrage-in-short-term-crypto-markets/)
- Crypto fees started on 15-minute contracts on Jan 5 2026 and covered all crypto timeframes by Mar 6 2026 — [Pine Analytics](https://pineanalytics.substack.com/p/polymarket-fee-rollout)
- By late 2026, a third-party guide describes maker rebates of 20% of taker fees in crypto, 25% in most categories and up to 50% in finance. This implies taker fees now exist across most categories (verify against official docs) — [StartPolymarket guide](https://startpolymarket.com/strategies/market-making/)
- Kalshi's pre-2025 taker fee was $0.07·P·(1−P) per contract, about 1.77% of a 50¢ contract after round-up. Kalshi began charging makers after April 2025 — [Bürgi, Deng & Whelan, Jan 2026](https://www.karlwhelan.com/Papers/Kalshi.pdf)

### Inferences
- The $40M figure is mostly a 2024 phenomenon, driven by election-season volume, thin books and a zero-fee regime. Several things have changed since:
  - taker fees on Polymarket (January–March 2026 onward)
  - maker fees on Kalshi (after April 2025)
  - many more bots
  - Expect intra-market YES+NO<$1 gaps to now close in seconds and to be net-negative for anyone paying taker fees on both legs. Retail edge here is likely negligible.
- NegRisk multi-outcome markets were where most of the money was. They require watching many outcomes at once and acting fast during volatility, which is a bot job. A retail operator with a modest VPS and websocket feed could still catch occasional large dislocations in low-attention multi-outcome markets. Capacity per opportunity is small, though: the paper's combinatorial opportunities averaged about $100 of maximum profit, which implies thin liquidity.
- Combinatorial arbitrage via LLM dependency detection is intellectually attractive but empirically tiny ($95K over a year). The LLM's false-positive rate was very high: 13 true pairs out of 1,576 flagged.
- Cross-platform arbitrage is best thought of as "resolution-risk arbitrage": the 2–4% average gap is roughly the market's price for wording, timing and settlement mismatch plus capital lockup. For retail it can work only with:
  - careful reading of both rulebooks
  - pre-funded accounts on both venues
  - tolerance for capital locked until resolution, which drags annualized returns on long-dated markets
- Polymarket international is not available to US persons (legal issues are covered elsewhere), which constrains who can even run Kalshi↔Polymarket arbitrage.

### Gaps
- No public on-chain study measures arbitrage profit on Polymarket after January 2026, i.e., post-fees.
- No study measures the latency to close YES+NO<$1 gaps in 2026. Vendor claims of "one block, about 2 seconds" are unverified.
- No verified dollar-loss case study of a Kalshi–Polymarket resolution mismatch was found.
- Who captured cross-venue arbitrage is undocumented.

---

## 2. Market making and liquidity provision

### Takeaway
This is the most consistently evidenced profitable activity on both platforms.
- Kalshi data show makers beat takers by about 22 percentage points.
- Kalshi market makers earned about $34.9M on the November 2026 midterms while takers lost about $44.6M.
- On Polymarket 15-minute crypto markets, makers won fewer fills but netted positive P&L.

However, the profits concentrate in professional firms (Susquehanna and others) and in well-engineered bots. Open-source MM bots are now described by their own maintainers as unprofitable or likely to lose money. Retail-scale MM runs into adverse selection, especially around news, and into crowded reward pools.

### Cited Findings
**Kalshi: maker vs taker returns (verified, academic)**
- Bürgi, Deng & Whelan, "Makers and Takers: The Economics of the Kalshi Prediction Market" (UCD, Jan 2026 version; GWU WP Feb 2026; CEPR DP) — [PDF](https://www.karlwhelan.com/Papers/Kalshi.pdf):
  - Sample: 46,282 contracts from 12,403 events, 2021 to April 2025, over 300,000 prices.
  - Average post-fee return was −9.64% for maker-bought contracts and −31.46% for taker-bought contracts.
  - Makers buying contracts priced ≥50¢ earned about +2.6% after fees, with a standard deviation of 33%.
- The authors' reasons why maker profits on favorites are not competed away — [PDF](https://www.karlwhelan.com/Papers/Kalshi.pdf):
  - Small volumes: average final volume in the top decile of markets was only $526,245, and the order books shown are thin.
  - High variance.
  - Lack of awareness. They explicitly flag the anomaly may disappear after publication.

**Kalshi: who the market makers are, and programs**
- Kalshi named Susquehanna International Group its first dedicated institutional market maker in 2024. A third-party guide reports this added about 30× liquidity in select markets — [Turbine guide](https://www.turbinefi.com/blog/how-to-market-make-prediction-markets-2026)
- Aug 19 2026: Cantor Fitzgerald began brokering block trades on Kalshi event contracts for clients, with Susquehanna providing pricing and liquidity. Kalshi's first block trade was in April 2026. CNBC discloses a commercial relationship and minority investment in Kalshi — [CNBC](https://www.cnbc.com/2026/08/19/hedge-funds-are-about-to-jump-in-big-to-prediction-markets.html)
- Jump Trading was reported to be taking equity stakes in Kalshi and Polymarket in connection with providing liquidity (headline-level only; details not verified) — [DeFi Rate](https://defirate.com/news/equity-for-liquidity-jump-trading-set-to-take-stakes-in-kalshi-and-polymarket/)
- Midterm elections (Nov 2026), from an InGame analysis summarized by CDC Gaming on Nov 10 2026: Kalshi takers lost $44.6M after fees and market makers earned $34.9M. Two Texas statewide races, House/Senate control, and the Michigan and Maine Senate races were large MM wins. Methodology not disclosed in the summary — [CDC Gaming](https://cdcgaming.com/brief/kalshi-market-makers-record-big-profits-as-takers-lose-on-midterm-elections/)
- Kalshi Liquidity Incentive Program, per CFTC filings — [CFTC Jul 15 2026 filing](https://www.cftc.gov/filings/orgrules/rules07152610358.pdf); [CFTC Oct 14 2026 filing](https://www.cftc.gov/filings/orgrules/rules10142633803.pdf):
  - Amended Feb 11 and Jul 15 2026, running into 2027.
  - A separate "Designated Liquidity Provider Market Making Program" (renamed Oct 14 2026) requires a signed Market Maker Agreement. Incentive periods are capped at 90 days.
- An analysis of the filings reports caps of $1,000 per market per day for the open tier and $50,000 per series per week for the MM tier. MM rates are in confidential exhibits and were revised in March 2026 for the new fee structure — [Navnoor Bawa analysis](https://www.navnoorbawaresearch.com/p/kalshi-publishes-one-liquidity-subsidy)
- Kalshi said it will end its Volume Incentive Program no earlier than Oct 13 2026, amid wash-trading allegations. Kalshi denies wash trading and attributes the repeated prints to fixed MM quotes hit by faster traders — [The Block, Sep 30 2026](https://www.theblock.co/news/business/2026-09-30-kalshi-ends-trader-incentive-program-417247)

**Polymarket: programs**
- Liquidity Rewards (quote-based):
  - Resting limit orders are automatically eligible.
  - Paid daily at midnight UTC.
  - The score rewards participation, boosts two-sided depth (one-sided orders still score) and favors tight spreads near the size-adjusted midpoint.
  - Modeled on dYdX's LP rewards. Minimum $1 payout.
  - [Polymarket docs](https://docs.polymarket.com/market-makers/liquidity-rewards)
- Polymarket distributed more than $5M in liquidity incentives in April 2026 across sports and esports. The World Cup 2026 pools (Jun 11 – Jul 19) were split into pre-game and in-play — [Polymarket docs](https://docs.polymarket.com/market-makers/liquidity-rewards)
- Maker Rebates (funded by taker fees):
  - Paid daily in pUSD, based on your share of liquidity that actually got taken.
  - Rebates use the same curve as taker fees and are computed per market, so you compete only with makers in that market.
  - [Polymarket docs](https://docs.polymarket.com/programs/maker-rebates)
- Polymarket US (CFTC-regulated QCX) runs a series-based MM program. Qualifying requires at least 5% of a series' monthly maker notional — [Polymarket docs / CFTC filing summary](https://docs.polymarket.com/programs/taker-rebates)
- A developer analysis says the rebate share fell from 100% of fees to 20% (crypto), which "significantly changes the economics" (secondary; verify) — [DEV Community](https://dev.to/emilanielsen/polymarkets-new-fee-structure-why-many-trading-bots-may-no-longer-be-profitable-2j3j)

**Polymarket: documented MM results**
- 15-minute crypto markets, week of Feb 2–8 2026, on-chain fills (Telonex): takers were ahead on 53% of executions but net negative. Makers won only 47% of fills yet netted about +$728,501 for the week. Profitable wallets existed in pure-maker, pure-taker and hybrid profiles — [Telonex](https://telonex.io/research/top-crypto-traders-polymarket-15m)
- 5/15-minute BTC, Nov 1–7 2026, 10.9M fills across 2,654 windows and 23,104 wallets (Polbots, a bot-listing site):
  - About 70% of wallets lost money.
  - Prices were accurate to about 1¢.
  - Takers paid $808K in fees and lost $952K.
  - Makers who quoted all day were ahead.
  - [Polbots](https://polbots.com/bots/btc-15-minute)
- Bitquery, one measured week in the 5/15-minute markets: the worst wallet (more than 15,000 markets, almost no fees because it mostly rested orders) lost more than the best wallet gained. Being a maker is not sufficient — [Bitquery](https://www.bitquery.io/investigations/polymarket-five-minute-casino)
- The polytrading.app leaderboard shows wallets with about $250 of 30-day rewards had 30-day P&L anywhere from −$16.0K to +$151.3K, so reward income is small next to inventory P&L — [polytrading.app](https://polytrading.app/market-makers)
- Open-source "poly-maker" (warproxxx):
  - The current README says MM on Polymarket "is competitive and can lose money" and calls the project a reference implementation.
  - A fork's README says "in today's market, this bot is not profitable and will lose money."
  - [warproxxx/poly-maker](https://github.com/warproxxx/poly-maker); [itgoyo fork](https://github.com/itgoyo/poly-maker)
- A developer who ran a cloned Polymarket MM bot reported that maker rewards and spread income were positive, but net P&L was negative after bugs, testing losses and directional hits (anecdote) — [DEV Community](https://dev.to/fatherson/i-cloned-a-polymarket-market-making-bot-and-ran-it-heres-what-i-learned-46ag)
- Solidus Labs (Polymarket politics, Dec 2025 – Feb 2026): 0.55% of profitable maker wallets captured 50% of maker gains, about $8M of about $16M. About 15% of volume in some markets looked like self-trading or incentive farming. Solidus sells surveillance tools — [CoinDesk, Apr 29 2026](https://www.coindesk.com/markets/2026/04/29/a-tiny-group-is-winning-on-polymarket-as-under-1-of-wallets-take-half-the-profits)

### Inferences
- Market making is the structural "house" position in a fee-on-taker, retail-dominated venue. The academic and on-chain evidence agrees that makers as a class beat takers. But maker P&L is highly concentrated, and passive quoting by itself loses to adverse selection: informed takers and news.
- Retail-feasible variants:
  - **(a) Passive limit-order discipline.** Always post rather than take, which captures part of the maker advantage without running a full MM book. This is the single most evidence-backed change a retail trader can make.
  - **(b) Reward farming** in long-dated, low-volatility markets with small size. Rewards are modest, pools crowd quickly, and news jumps can wipe out months of rewards.
  - **(c) Two-sided MM in niche markets** where pros are absent. This needs automated quote management with kill-switches around scheduled news.
- Competition is rising fast: Susquehanna, Jump and others, hedge-fund block flow, and Kalshi's DLP program limited to signed MMs. Kalshi's top-tier incentives are not open to retail.
- Expect top-of-book MM in liquid sports, election and crypto markets to be uncompetitive for an individual. The Kalshi paper's own argument (thin books, high variance) suggests residual opportunity is in smaller markets, where capacity is a few hundred to a few thousand dollars per market.

### Gaps
- No audited, public P&L write-up by an identified Polymarket or Kalshi market maker for 2026 was found.
- Early-period claims (e.g., LPs earning about 200–300 USDC/day on about 10K USDC) surfaced in guides, but I could not pin them to a primary source.
- Kalshi MM-tier incentive rates are confidential.
- Total annual Polymarket LP reward payouts for 2026 were not found in a primary source.

---

## 3. Behavioral biases: favorite–longshot, "bond"/near-certain strategy, news reaction, timing, sports

### Takeaway
The favorite–longshot bias (FLB) is well documented on both Kalshi and Polymarket:
- Longshots under 10¢ lose 19–60%+.
- Favorites earn small positive returns: about +2.6% for Kalshi makers on contracts ≥50¢, and about 0.2–0.8¢ per dollar for Polymarket favorites ≥90¢.

The favorite side is thin, high-variance and showing signs of decay: the Kalshi 2025 coefficient is smaller, and the bias is absent in Polymarket sports. The "bond" strategy of buying 95–99¢ contracts is a small positive-expectancy, negatively skewed trade. One loss erases about 19 wins at 95¢, and the main risks are resolution disputes and exit liquidity. Evidence on systematic over- or underreaction and weekend effects is thin and mostly unverified. Sports prices on the exchanges track Pinnacle closely, with no FLB in Polymarket sports, so the "beat sportsbooks" edge is mostly about lower vig, not mispricing.

### Cited Findings
**Favorite–longshot bias on Kalshi (Bürgi, Deng & Whelan, Jan 2026 version, data 2021 to Apr 2025)** — [PDF](https://www.karlwhelan.com/Papers/Kalshi.pdf)
- Contracts costing ≤10¢ lose over 60% of money after fees.
- Contracts above 50¢ earn small positive returns, statistically significant above 70¢.
- Average return across contracts: about −20% pre-fee and −22% with fees.
- About two-thirds of prices sit at <10¢ or >90¢: 106,209 contracts in each band.
- Worked examples: a 5¢ contract that wins 3% of the time returns −40% before fees. A 95¢ contract that wins 98% of the time returns +3.1% before fees.
- The FLB holds in every category: financials, climate and weather, crypto, politics, entertainment, economics. It is smaller in politics and entertainment.
- It is not explained by volume or trade size. The largest-trade quintile has the largest bias.
- Decay: the bias coefficient was 0.048 in 2024 vs 0.021 in 2025, the latter significant only at 10%. The authors note "some evidence that the bias in prices is diminishing over time."
- Mechanism: modest belief disagreement plus a small overweighting of low probabilities. Takers have more extreme beliefs.

**Favorite–longshot bias on Polymarket (Cardozo & Rivero-Wildemauwe, arXiv 2609.12878, Sep 11 2026; 588M trades, 2.48M accounts)** — [arXiv](https://arxiv.org/abs/2609.12878)
- Purchases below 10¢ lose 19.3¢ per dollar. Purchases at or above 90¢ earn 0.83¢ per dollar (observed flows).
- Magnitude depends on aggregation:
  - Equal-weighted contracts: longshots lose 6.3¢.
  - Grouped by parent event: longshots gain 4.1¢.
- Equal-weighted favorites at 90–99¢ return about 0.19% per purchase, 95% CI [0.11%, 0.27%] — [secondary excerpt via search of the same paper](https://arxiv.org/pdf/2609.12878)
- The two-sided pattern is robust in crypto and politics but "surprisingly absent" in sports.
- Accounts that buy favorites most heavily earn less than other accounts.
- A separate trade-tape dataset paper (Polymarket-v1, arXiv 2606.04217) reports negative realized returns for tokens priced ≤0.30 and positive for ≥0.40 (seen via search excerpt) — [arXiv 2606.04217](https://arxiv.org/pdf/2606.04217)

**"Bond" / near-certain strategy (buy 90–99¢ near resolution)**
- Typical per-trade return is 1–5%. A 95¢ entry yields about 5.3% if correct, and a 97¢ entry about 3.1% — [StartPolymarket bonding guide](https://startpolymarket.com/strategies/bonding/)
- Exit liquidity thins near resolution. Polymarket's own docs give an example of a contract near 97¢ filling a sell at 94¢ — [Polymarket US docs](https://docs.polymarket.us/learn/trading/prices-and-fees/price-slippage)
- Above 98¢ the remaining stub is typically days or hours and the order book is thin (blog analysis) — [Medium, "Picking up nickels at ninety-nine cents"](https://medium.com/@jacek.jurczynski/picking-up-nickels-at-ninety-nine-cents-d4308907db2c)
- It is a directional trade, not arbitrage, if the adverse outcome is still possible — [QuantVPS](https://www.quantvps.com/blog/polymarket-hft-traders-use-ai-arbitrage-mispricing)
- An RL forecasting model's profits came mostly from 40–60% markets. On markets where Polymarket was highly confident, the best model was not statistically better than chance at betting against the market — [arXiv 2505.17989](https://arxiv.org/pdf/2505.17989)

**News over- and underreaction**
- Tsang & Yang (arXiv 2603.03152, v4 Jul 2026), Polymarket 2024 election on-chain data — [arXiv](https://arxiv.org/abs/2603.03152):
  - The post-debate price rise largely reversed (transitory overshoot).
  - The assassination-attempt repricing persisted.
  - Biden's withdrawal drew the heaviest trading but little change in the Trump price.
  - Price response depends on information content and anticipation, not volume.
- Tsang & Yang (arXiv 2603.03136, v3 Sep 2026) — [arXiv](https://arxiv.org/abs/2603.03136):
  - Naive Polymarket volume overstates turnover. October Trump-market turnover was $391M vs $958M naive.
  - Moving the October forecast 5pp cost about $9.1M. Markets are shallower than raw volume suggests, especially young, thin markets.
- Reported: Polymarket takes about 80 minutes to fully reprice after major news, with most movement in the first 1–30 minutes, and a price-response coefficient of about 0.64 vs a public-data benchmark. The primary study is not named, so this is unverified — [Crypto Briefing](https://cryptobriefing.com/polymarket-repricing-lag-80-minutes/)

**Weekend and time-of-day effects**
- Talk slides (Jan 2026) on Polymarket crypto-threshold contracts vs options-implied probabilities: gaps widen on weekends and announcement days, attributed to thin liquidity and attention bursts (not peer-reviewed) — [slides](https://sns-defi.github.io/talks/market-efficiency-in-prediction-markets-a-comparison-with-derivatives.pdf)

**Sports vs sportsbooks**
- Vendor snapshot, 88 fixtures on Oct 13 2026, winner markets:
  - Median margin: Polymarket 1.00%, Kalshi 1.02%, Pinnacle 4.02%, bet365 6.70%.
  - Median distance from de-vigged Pinnacle: Polymarket 0.59pp, Kalshi 0.75pp, bet365 0.83pp.
  - [OddsPapi](https://oddspapi.io/blog/polymarket-api-kalshi-api-vs-sportsbooks-the-developers-guide/)
- Single-game pre-game divergences of about 5.7pp between Kalshi and FanDuel were documented five days out, converging before the event — [Blockworks Research](https://app.blockworks.com/report/from-betting-to-trading-how-kalshi-is-reshaping-sports-markets)
- Price-discovery paper (Polymarket, Betfair, Kalshi, sportsbooks): Kalshi's share of price discovery was already non-trivial within about a month of its Oct 2024 launch. Short sample — [Boğaziçi WP](https://web.bogazici.edu.tr/torul/pridis.pdf)
- The FLB is absent in Polymarket sports — [Cardozo & Rivero-Wildemauwe](https://arxiv.org/abs/2609.12878)

### Inferences
- The most robust behavioral rule is negative: avoid buying longshots, especially as a taker. The positive side has an expected edge of roughly 0.2–3% per trade. Sizing it needs hundreds to thousands of independent bets to verify, and the 33% standard deviation (Kalshi makers ≥50¢) means drawdowns are routine.
- The Kalshi paper explicitly invites decay after publication, and the 2025 coefficient already halved. Treat "buy favorites as a maker" as a small, shrinking edge, plausibly less than 1–2% net in 2026, and best harvested passively (limit orders) in less-liquid markets.
- The bond strategy's real risks are idiosyncratic:
  - resolution disputes and ambiguous wording
  - delayed settlement, which locks capital
  - sudden reversals
  - illiquid exits
  - Correlated losses (many near-certain markets failing on one shock) are the tail. Positions should be diversified across unrelated events, with explicit caps per event.
- Sports exchanges are anchored to sharp books. A retail edge would have to come from line-shopping against slow books or lower vig, not from systematic exchange mispricing. CLV vs Pinnacle is the right benchmark.

### Gaps
- No rigorous study of time-of-day or weekend effects on Kalshi or Polymarket event (non-crypto) markets.
- No primary source for the "0.64 coefficient / 80-minute repricing" claim.
- No closing-line study of exchange sports markets vs Pinnacle across many games.
- No net-of-fee test of a systematic bond strategy on Polymarket after the 2026 fee changes.

---

## 4. Speed and latency strategies (short-duration crypto, data and news releases)

### Takeaway
The 5- and 15-minute crypto up/down markets were the 2025–early 2026 bot gold rush. Bots priced off Binance and Coinbase spot ahead of a lagging Polymarket book. Claimed returns included $313 → about $414–438K in about a month for one wallet, but those are unverified and contradicted elsewhere. Polymarket then responded:
- Dynamic taker fees from January 2026, about $150M charged through mid-August 2026.
- Settlement-design changes after manipulation research.

These are now professionalized maker-bot markets: bots are 55–62% of volume. Takers lose in aggregate, and sub-100ms infrastructure and maker-side quoting are prerequisites. A retail latency play here is very unlikely to be viable. News and data-release latency (econ data, weather, mention markets) is similarly bot-contested, and the regulators have flagged mention markets.

### Cited Findings
- Fast-markets bot share (Dune), with fast-market volume as context — [Dune](https://dune.com/blog/polymarket-fast-markets):
  - Bots were 62% of volume in 15-minute markets and 55% in 5-minute markets.
  - The average bot trade was about $6–7, vs $15–25 for casual traders.
  - 5-minute markets did about 3× the notional of 15-minute markets between Feb 15 and Mar 30 2026.
- Bitquery forensics, Sep 1 2025 – Aug 18 2026 — [Bitquery](https://www.bitquery.io/investigations/polymarket-five-minute-casino):
  - 679M matched trades across 819,457 buying wallets in 5/15-minute markets.
  - Volume peaked at about $1.12B in March 2026. BTC was 74.5% of volume.
  - Taker fees totaled about $150M from January to mid-August 2026, with the effective rate peaking at 4.22% in March 2026 and roughly halving from May.
  - In one measured week, the crowd was within 0.1% of zero before fees and down by about the full fee after fees.
  - About 31% of wallets finished ahead.
  - Losses scaled with trading frequency.
- Polbots, Nov 1–7 2026: about 70% of wallets lost. Takers paid $808K in fees and lost $952K. Prices were accurate to about 1¢. Spot exchanges are said to lead the Polymarket book by "seconds" (no measurement given) — [Polbots](https://polbots.com/bots/btc-15-minute)
- Polymarket stated the January 2026 taker fee was meant to "neutralise" latency arbitrage. Observers expected pure taker bots to shrink and maker-style bots to gain — [Finance Magnates](https://www.financemagnates.com/cryptocurrency/polymarket-introduces-dynamic-fees-to-curb-latency-arbitrage-in-short-term-crypto-markets/); [The Block](https://www.theblock.co/post/384461/polymarket-adds-taker-fees-to-15-minute-crypto-markets-to-fund-liquidity-rebates)
- A backtest across 1,233 order books found active taker bots lost −14.6% to −53.4% after fees. It assumed a flat 2% fee and is not peer-reviewed — [The Data Scientist](https://thedatascientist.com/why-polymarket-trading-bots-arbitrage-lose-money-backtest/)
- Claimed bot profits (anecdote; not verified on-chain by these outlets) — [Yahoo Finance / BeInCrypto, Jan 6 2026](https://finance.yahoo.com/news/arbitrage-bots-dominate-polymarket-millions-100000888.html):
  - A latency bot reportedly turned $313 into about $414K in one month on BTC/ETH/SOL 15-minute markets. It reportedly bet $4–5K per trade with a 98% win rate, buying when the true probability was about 85% but the market still showed 50/50.
  - An "AI bot" reportedly made $2.2M in two months.
  - A front-running bot traded ahead of market orders in thin books.
- The same "0x8dxd" profile is cited elsewhere as $313 → about $438K by Jan 6 2026 with 98% accuracy, but a February 2026 snapshot reportedly showed 13,000+ predictions at a 53% win rate. The figures conflict — [ai-checker/webcoda summary](https://ai-checker.webcoda.com.au/articles/ai-bots-polymarket-trading-profits-40-million-2026)
- Settlement manipulation (Stanford and Singapore Management University working paper, "Settlement Manipulation in Prediction Markets"):
  - About 16,000 five-minute BTC contracts from their Feb 12 2026 launch through April.
  - About $8.2M went to 821 traders who moved spot price near window close, against the Chainlink settlement.
  - Extending windows to 15 minutes largely eliminated the effect.
  - [Bloomberg Law](https://news.bloomberglaw.com/crypto/stanford-study-says-polymarket-crypto-bets-are-being-manipulated); [Bitcoin Magazine](https://bitcoinmagazine.com/news/traders-took-8-2-million-from-polymarkets)
- Economic data: Kalshi's modal fed-funds forecast had a perfect record the day before FOMC meetings, a significant improvement over fed funds futures. Kalshi headline-CPI expectations significantly beat the Bloomberg consensus. Core CPI and unemployment were no better than consensus — [Federal Reserve FEDS 2026-010, Diercks, Katz & Wright](https://www.federalreserve.gov/econres/feds/files/2026010pap.pdf)
- Mention markets:
  - Kalshi pulled sports mention markets in August 2026 amid a reported CFTC review. The CFTC later issued an advisory on heightened manipulation risk (not a ban) — [NPR, Aug 13 2026](https://www.npr.org/2026/08/13/nx-s1-5930689/cftc-probe-mention-markets-prediction-markets-kalshi); [DeFi Rate](https://defirate.com/news/kalshi-pulls-sports-mention-markets-cftc-probe/); [Cointelegraph](https://cointelegraph.com/news/cftc-issues-warning-over-risky-prediction-market-mention-contracts)
  - Coinbase's CEO deliberately read mention-market terms on the Q3 2025 earnings call — [DeFi Rate](https://defirate.com/prediction-markets/mention-markets/)
  - Kalshi does not publish an automated-volume share — [search summary; DeFi Rate mention guide](https://defirate.com/prediction-markets/mention-markets/)

### Inferences
- Short-duration crypto markets are now a maker-bot arena:
  - Taker fees peak near 50¢, exactly where latency trades happen.
  - Exchange spot leads by seconds, and professional bots co-locate and quote.
  - Settlement rules have been changed to resist manipulation.
  - Retail takers here are the documented losers: about 70% of wallets lose, and losses scale with activity.
  - This edge has decayed for anyone without sub-second infrastructure and a maker-side design.
- Data-release latency is in principle cleaner: the event is a scheduled number with known resolution. But it competes with HFT-grade firms (Susquehanna-class makers pull or reprice quotes instantly), and Kalshi's macro markets are already more accurate than consensus. Edge, if any, is in nowcasting before the release (a forecasting problem), not in reacting after it.
- Mention markets have a regulatory overhang, insider and speaker-manipulation risk, and transcript-based resolution quirks. The edge is speaker-habit research, not speed.

### Gaps
- No 2026 on-chain study separates P&L for latency bots vs maker bots vs retail in the fast markets.
- No verified wallet-level audit of the famous "$313 → $400K+" bot.
- One secondary search result reported that Polymarket moved 5- and 15-minute settlement to a Chainlink TWAP (60-second window) in August 2026, which would fit the manipulation findings. I could not confirm the primary source.
- No public measurement of Kalshi latency competition on economic data or weather releases.

---

## 5. Information and domain edges: weather, economic nowcasting, mention/word markets, niche markets

### Takeaway
Domain-model edges are plausible because the markets are new, thin and retail-heavy, and the FLB holds in Kalshi's weather and economics categories. But the best evidence shows these markets are already strong forecasters:
- Kalshi temperature prices beat the National Blend of Models in 6 of 7 cities.
- Kalshi beats the Bloomberg consensus on headline CPI.

Edge would have to come from beating the market price, not the public models. No audited retail P&L exists for these strategies. Vendor tools proliferate, which suggests crowding of the obvious "NOAA/ensemble vs price" signal.

### Cited Findings
- Weather (Crosier study, seen via secondary summary): Kalshi temperature markets in seven US cities beat the National Blend of Models, the most accurate public forecast studied, in 6 of 7 cities. The advantage persisted overnight into the forecast day. The summary notes Kalshi's edge narrows against combined forecasts — [NextPredict summary](https://nextpredict.io/market-news/industry/study-kalshi-weather-markets-outperform-public-forecasts/)
- Practitioner guidance (vendor) — [Turbine weather guide](https://www.turbinefi.com/blog/how-to-trade-kalshi-weather-markets-2026):
  - Same-day markets already embed observed temperatures.
  - Correcting a model's 30-day bias is credited with about 0.7°F improvement at short leads, which matters because strikes are spaced 1–2°F apart.
  - Skill decays toward climatology by about day 10.
  - A 3¢ apparent edge can vanish after fees and slippage.
- Vendor tools scan 200+ weather markets for more than 10% edge and display about 65% win rates (unverified marketing). Their own example arithmetic is wrong — [Kalshi Weather Edge](https://www.kalshiweatheredge.com/)
- The Kalshi FLB is present in the climate & weather and economics categories — [Bürgi, Deng & Whelan](https://www.karlwhelan.com/Papers/Kalshi.pdf)
- Economic data:
  - Fed FEDS 2026-010: Kalshi headline CPI significantly beats the Bloomberg consensus. Core CPI and unemployment are statistically similar to consensus. The authors warn tails are noisy in illiquid markets — [Federal Reserve](https://www.federalreserve.gov/econres/feds/files/2026010pap.pdf)
  - Kalshi's self-published research claims 40.1% lower MAE than consensus (Feb 2023 – mid-2025) and a 75% win rate when the market and consensus differ by ≥0.1pp — [Kalshi Research](https://kalshi.com/research/publications/crisis-alpha)
  - Kalshi's July 2026 preview: median headline-CPI (YoY) error of 6.7bp vs 8.9bp for consensus across 36 one-week-ahead observations — [Kalshi Research](https://kalshi.com/research/insights/july-cpi-preview)
  - Independent coverage calls the accuracy claims contested — [Yahoo Finance](https://finance.yahoo.com/news/kalshi-claims-beats-wall-street-160215485.html)
- Hedge-fund and Cantor clients are expected to focus on Kalshi's climate, weather and economic-indicator markets (Aug 2026) — [CNBC](https://www.cnbc.com/2026/08/19/hedge-funds-are-about-to-jump-in-big-to-prediction-markets.html)
- Mention/word markets:
  - A personal analysis of Fed-speech word markets found only 25.8% of late-added words resolved Yes (small-sample anecdote) — [pjrigali](https://pjrigali.github.io/posts/Kalshi_Fed_Analysis)
  - Resolution typically uses the official investor-relations transcript posted within about 24 hours. Kalshi changed its contract language after the Coinbase episode — [DeFi Rate](https://defirate.com/prediction-markets/mention-markets/)
- Niche and low-attention markets: Tsang & Yang find price-impact overstatement is largest in thin, young markets. The arbitrage paper finds opportunities cluster in low-liquidity periods — [arXiv 2603.03136](https://arxiv.org/abs/2603.03136); [arXiv 2508.03474](https://arxiv.org/html/2508.03474)
- Insider-like flow is a hazard in niche markets. Gómez-Cram et al. flag 1,950 accounts that opened shortly before a single event and went dormant afterward. These accounts move prices 7–12× more per dollar than skilled traders. In one case, three accounts made over $630K on Maduro's ouster — [The Block](https://www.theblock.co/post/398902/skilled-polymarket-traders-are-a-3-minority-and-everyone-else-funds-their-gains-study)

### Inferences
- Weather is the most tractable domain edge for a technically capable individual. Data is free (NOAA/NBM/GFS/ECMWF ensembles, station observations), resolution is objective, and markets are daily and repeated, so statistical evaluation is fast.
  - But "public model vs price" is the obvious signal and is crowded by vendor tools.
  - Durable edge would need station-specific bias correction, intraday observation nowcasting, and maker-side execution.
  - Capacity is small: individual brackets are thin.
- Economic nowcasting: the market already beats consensus on headline CPI, so a retail nowcast must beat both the consensus and the market. Plausible edge is limited to a few high-signal releases, and institutional entrants (Cantor clients) are targeting exactly these markets. Low capacity, high competition.
- Mention markets: a speaker-habit base-rate model (frequency of terms across past transcripts) is a reasonable LLM-assisted edge. But regulatory risk (CFTC review and advisory), insider and manipulation risk, and resolution quirks make it fragile.
- Niche markets: more mispricing, but also more insider flow. Absence of competition is often absence of liquidity.

### Gaps
- I could not access the full Crosier weather paper. No audited P&L from any weather-model trader was found.
- No independent study of retail nowcasting P&L on Kalshi CPI or jobs markets.
- No quantitative study of mention-market calibration across many events.

---

## 6. Copy-trading and whale-following

### Takeaway
The best available evidence says copying top-P&L wallets does not produce reliable net gains:
- Past-to-future return correlation is near zero.
- One- or two-cent worse fills flip profits to losses.
- Much leaderboard P&L (MM spreads, rewards, split/merge arbitrage) is uncopyable.

Genuine skill exists but is a roughly 3% minority, and raw P&L identifies it poorly: only 12% of top earners are "skilled." Most copy-trading evidence comes from vendors.

### Cited Findings
- OrcaLayer walk-forward backtest (a data vendor; code public) — [OrcaLayer](https://orcalayer.com/blog/polymarket-copy-trading-whales-backtest); [GitHub](https://github.com/orcalayer/polymarket-copy-trading-whales-backtest):
  - Method: rank wallets on the prior two months, then copy each one's first buy per market the next month.
  - NFL picks ranged from −$1.63 to +$1.46 per $10, with no month reaching t=2.
  - In League of Legends, all 12 results were negative.
  - At +1¢ entry slippage, the average wallet lost 31–63¢ per $10 in every MLB month.
  - Attributed to selection on luck.
- Shark Radar (tracker vendor; underlying backtests not named): 0.035 correlation between past and future returns across 157 top wallets, and −13.6% out-of-sample return from copying the top 15 by profit — [Shark Radar](https://sharkradar.app/polymarket-copy-trading)
- In one example, a profitable tennis wallet recomputed with entries 2¢ worse went from +$191K to −$64K. Some "high win-rate" wallets never close losers: the top monthly wallet's win rate fell from 87.7% to 42.2% once all losers were counted. Multi-wallet operators distort per-wallet P&L — [DEV Community](https://dev.to/jacobyf/the-polymarket-copy-trading-trap-what-nobody-tells-you-about-following-prediction-market-whales-27b5)
- Gómez-Cram, Guo, Kung (LBS) & Jensen (Yale), SSRN 6617059, revised Apr 25 2026 — [The Block](https://www.theblock.co/post/398902/skilled-polymarket-traders-are-a-3-minority-and-everyone-else-funds-their-gains-study):
  - Data: all Polymarket trades 2023–2025, 1.72M accounts, 210,322 markets, $13.76B volume.
  - 3.14% of accounts are "skilled winners," identified by a sign-randomization test with 10,000 shuffles.
  - Only 12% of top earners are in the skilled group, and about 60% of "lucky winners" reverted to losses out of sample.
  - 44% of skilled accounts stayed skilled in the holdout sample, vs about 10% persistence for active mutual funds.
- Vendor claims are weak (anecdote):
  - Launchpoly: copiers earn 8–12% vs 20%+ for top whales (30-day, single author, no method) — [Launchpoly](https://launchpoly.com/blog/polymarket-whale-tracking-study)
  - Polyloly: a top cohort returned +81.6% on only 62 trades — [Polyloly](https://polyloly.com/blog/where-polymarket-edge-lives-cohort-roi-analysis)

### Inferences
- Copy-trading on raw leaderboard P&L should be treated as negative-expectancy after slippage and fees. If used at all, it should be:
  - a signal input, e.g., skill-filtered wallets identified with randomization or out-of-sample tests;
  - in slow-moving markets where a 1–2¢ worse entry is small relative to edge;
  - never in fast in-play or crypto markets.
- Following wallets is also hazardous because some "smart money" is insider flow on one-off events, which doesn't persist.

### Gaps
- No peer-reviewed test of a realistic, slippage-aware copy strategy using skill-classified (not P&L-ranked) wallets.

---

## 7. Who profits on Polymarket and Kalshi overall

### Takeaway
Most accounts lose: roughly 67–85% of wallets, depending on study and period. Profits are extremely concentrated: the top 1% of winners take about 50–85%+ of profits. Winners are disproportionately market makers, bots and a small persistent skilled minority, plus insiders on specific events. Takers and frequent small traders fund them, especially after fees. Institutional market makers (Susquehanna on Kalshi; Jump reportedly on both venues) and hedge-fund block flow arrived in 2024–2026, so competition is rising.

### Cited Findings
- Akey, Grégoire, Harvie & Martineau, "Who Wins and Who Loses in Prediction Markets? Evidence from Polymarket" (SSRN 6443103 / CEPR DP21615, 2026): 588M trades worth $67B. The top 1% of users with positive P&L capture 76.5% of profits, and the top 1% of losers bear 68.1% of losses. Monthly performance is "modestly persistent," possibly due to selection (via search summary; PDF blocked) — [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6443103); [CEPR](https://cepr.org/publications/dp21615)
- Gómez-Cram et al. (2026) — [The Block](https://www.theblock.co/post/398902/skilled-polymarket-traders-are-a-3-minority-and-everyone-else-funds-their-gains-study):
  - 3.14% skilled winners. Skilled winners plus market makers are under 3.5% of accounts but capture over 30% of gains.
  - The 67% of accounts classed as unlucky or unskilled losers absorb the platform's entire aggregate losses.
- Reichenbach & Walther (SSRN 5910522, Dec 2025): fewer than a third of traders earn positive profits, and profits persist over time (via search summary) — [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5910522)
- Motley Fool analysis reported Nov 2026: about 313,000 wallets across 210 markets resolved in 2025. About 17% of wallets were profitable. The top 1% of profitable wallets took about 85% of profits and the top 5% more than 96%. In sports, the top 1% took 94% — [KESQ/Stacker, Nov 5 2026](https://kesq.com/stacker-personal-finance-investing/2026/11/05/do-stocks-beat-prediction-markets-for-most-people-yes/)
- DeFi Oasis (Dec 2025): about 70% of Polymarket addresses lost money. Under 0.04% of addresses captured over 70% of realized profits, about $3.7B — [Yahoo Finance](https://finance.yahoo.com/news/70-polymarket-traders-lost-money-192327162.html)
- Solidus Labs (politics, Dec 2025 – Feb 2026): 0.55% of profitable makers and 0.26% of winning takers each took about half of their cohort's gains — [CoinDesk](https://www.coindesk.com/markets/2026/04/29/a-tiny-group-is-winning-on-polymarket-as-under-1-of-wallets-take-half-the-profits)
- Vultax monthly snapshot: single-trade wallets were profitable 12.2% of the time, vs 63.7% for wallets making 6–20 trades. 36 wallets took 44% of gains, and winners repeat 41–51% of the time — [Vultax](https://vultax.com/research/best-polymarket-traders-leaderboards)
- Fast crypto markets: about 70% of wallets lose (Nov 2026), and about 31% finished ahead in a Bitquery week — [Polbots](https://polbots.com/bots/btc-15-minute); [Bitquery](https://www.bitquery.io/investigations/polymarket-five-minute-casino)
- Kalshi: average return across contracts is about −22% with fees. Takers lose about 31% and makers about 10% — [Bürgi, Deng & Whelan](https://www.karlwhelan.com/Papers/Kalshi.pdf)
- Kalshi midterms (Nov 2026): MMs earned +$34.9M and takers lost −$44.6M after fees — [CDC Gaming / InGame](https://cdcgaming.com/brief/kalshi-market-makers-record-big-profits-as-takers-lose-on-midterm-elections/)
- Institutional entrants:
  - Susquehanna (Kalshi MM since 2024) — [Turbine](https://www.turbinefi.com/blog/how-to-market-make-prediction-markets-2026)
  - Cantor and Susquehanna block trades (Aug 2026) — [CNBC](https://www.cnbc.com/2026/08/19/hedge-funds-are-about-to-jump-in-big-to-prediction-markets.html)
  - Jump equity-for-liquidity (reported) — [DeFi Rate](https://defirate.com/news/equity-for-liquidity-jump-trading-set-to-take-stakes-in-kalshi-and-polymarket/)
- Caveats on all of the above:
  - Wallets are not people, since one operator can run many wallets.
  - Realized and unrealized P&L differ.
  - Several sources are vendors or have commercial interests (Solidus sells surveillance; CNBC has a Kalshi stake).
  - [Yahoo Finance](https://finance.yahoo.com/news/70-polymarket-traders-lost-money-192327162.html); [CoinDesk](https://www.coindesk.com/markets/2026/04/29/a-tiny-group-is-winning-on-polymarket-as-under-1-of-wallets-take-half-the-profits)

### Inferences
- The base rate for a new participant is losing money, and the default way to lose is taking liquidity frequently in fee-bearing markets.
- The populations that win are:
  - (1) liquidity providers;
  - (2) a small, persistent skilled group whose edge is information or forecasting;
  - (3) speed and arbitrage bots;
  - (4) insiders.
- Only (2) and a small-scale version of (1) are realistic for a retail individual.

**Cross-strategy viability summary for a retail individual with modest capital (late 2026; my synthesis)**

| Strategy | Evidence of edge | Crowding (late 2026) | Capacity for retail | Key risks | Retail realism |
|---|---|---|---|---|---|
| Intra-market YES+NO / NegRisk arbitrage | Strong (about $40M realized, 2024–25) | Very high (bots); fees since 2026 | Tiny per opportunity | Leg risk, fees, speed | Low |
| Combinatorial (logical-link) arbitrage | Weak (about $95K/yr) | Low–moderate | Tiny | Resolution/logic error | Low |
| Cross-platform arbitrage | Moderate (2–4% persistent gaps) | Moderate | Small–moderate | Rule mismatch, lockup, transfer delays, access | Low–medium (with careful rule-reading) |
| Market making / reward farming | Strong for makers as a class | High in liquid markets; institutions | Small in niche markets | Adverse selection, news jumps, reward crowding | Medium (niche, small, automated) |
| Passive limit orders instead of taking | Strong (makers −10% vs takers −31% on Kalshi) | n/a | n/a | Non-fill | High (do this regardless) |
| Favorite/"bond" buying | Moderate, small and decaying (+0.2% to +2.6%) | Rising | Moderate | Tail and resolution risk, illiquid exit | Medium (low return) |
| Avoid longshots | Strong | n/a | n/a | — | High (defensive rule) |
| 5/15-minute crypto latency | Was strong in 2025; now fee-killed for takers | Extreme (55–62% bots) | Small | Fees, infrastructure, manipulation | Very low |
| Data-release latency | Unclear | High (pro MMs) | Small | Speed, rule quirks | Low |
| Weather models | Plausible; markets already beat NBM | Rising (vendor tools) | Small | Model error, fees | Medium (best domain candidate) |
| Econ nowcasting | Market already beats consensus on headline CPI | Rising (institutions) | Small | Model error | Low–medium |
| Mention markets | Anecdotal | Moderate | Small | Regulatory, insider, manipulation | Low–medium |
| Copy-trading top P&L wallets | Negative in backtests | High | — | Slippage, luck selection | Very low |

### Gaps
- No comparable "who wins" study exists for Kalshi at the account level, because Kalshi data is not on-chain. Evidence is limited to contract-level returns and third-party midterm analysis.
- The full Akey et al. paper was not accessible (403), so maker/taker and bot breakdowns from it are not captured here.

---

## 8. Position sizing and evaluation practices (Kelly, bankroll, edge measurement, skill vs luck)

### Takeaway
For a binary contract bought at price P with estimated true probability p, full Kelly stakes (p − P)/(1 − P) of bankroll. Practitioners use fractional Kelly (¼–½) because probability-estimation error dominates. Fees must be folded into P. Edge should be measured against the market (log loss or Brier vs market price, closing-line value, randomization tests) rather than by win rate. Small edges need from several hundred to many thousands of independent bets to distinguish from luck.

### Cited Findings
- The Kelly fraction for a YES bought at P with belief p is (p − P)/(1 − P). Worked example: P=0.55, p=0.62 gives about 15.6% of bankroll at full Kelly. For NO, invert both p and P — [Navnoor Bawa, "The Math of Prediction Markets"](https://navnoorbawa.substack.com/p/the-math-of-prediction-markets-binary); [NexusFi position sizing](https://nexusfi.com/a/prediction-markets/position-sizing-binary-markets)
- Fractional Kelly (commonly ½) is used because a few points of probability error massively oversizes positions. If "62%" is really 57%, you are dramatically oversized — [NexusFi](https://nexusfi.com/a/prediction-markets/position-sizing-binary-markets)
- Theory: a fractional-Kelly bettor behaves like a full-Kelly bettor whose beliefs are a weighted blend of their own and the market's. This is a principled reason to shrink toward the market price — [arXiv 1201.6655](https://pdf.arxiv.org/pdf/1201.6655)
- Return variance is the binding constraint. Kalshi makers buying ≥50¢ contracts averaged +2.6% with a 33% standard deviation. The authors cite Samuelson and Pratt–Zeckhauser "proper risk aversion" as a reason rational investors may decline such bets — [Bürgi, Deng & Whelan](https://www.karlwhelan.com/Papers/Kalshi.pdf)
- Skill measurement in practice: a sign-randomization test re-runs each trader's history 10,000 times with random buy/sell flips. Raw P&L is a poor skill proxy: 12% overlap with skilled traders, and about 60% of lucky winners revert — [The Block on Gómez-Cram et al.](https://www.theblock.co/post/398902/skilled-polymarket-traders-are-a-3-minority-and-everyone-else-funds-their-gains-study)
- Win rate is misleading. Unclosed losers inflate win rates (87.7% → 42.2%). In 15-minute markets, takers won 53% of fills yet lost money — [DEV Community](https://dev.to/jacobyf/the-polymarket-copy-trading-trap-what-nobody-tells-you-about-following-prediction-market-whales-27b5); [Telonex](https://telonex.io/research/top-crypto-traders-polymarket-15m)
- Slippage-aware evaluation: model copy or entry fills at +1–2¢ worse — [OrcaLayer](https://orcalayer.com/blog/polymarket-copy-trading-whales-backtest)

### Inferences
- **Sample-size arithmetic** (my calculation; assumes independent bets and a t-stat of about 2): n ≈ (2σ/edge)².
  - 50¢ contracts: per-bet return σ ≈ 100% of stake. A 2% edge needs about 10,000 bets, and a 5% edge about 1,600.
  - 95¢ contracts: σ ≈ √(0.95·0.05)/0.95 ≈ 23%. A 1¢ edge (true 96% vs price 95¢, about 1.05% return) needs about 1,900 bets.
  - Kalshi maker-favorite figures (mean 2.6%, σ 33%) need about 650 contracts.
  - Correlated bets (same event, same news shock, same game) raise the required n substantially.
  - Practical implication: weather, daily econ, and other repeated objective markets are the only categories where a retail trader can accumulate enough independent samples within months.
- **Recommended evaluation stack** (practice synthesis; not from a single source):
  - Log loss or Brier score of your probabilities vs the market's price at your entry time. You must beat the market, not the outcome.
  - Closing-line value: did the price move toward you by resolution or by the close?
  - P&L after fees and realistic fills.
  - Out-of-sample or walk-forward testing, and randomization tests for luck.
- **Bankroll:** use ¼–½ Kelly on a market-shrunk probability, with hard per-event and per-correlated-cluster caps. Account for capital lockup: a 2% edge locked for 3 months is about 8% annualized before compounding and losses. Count fees, including Kalshi maker fees after April 2025 and Polymarket taker fees since 2026, in P before sizing.

### Gaps
- No published dataset of closing-line value for retail prediction-market traders.
- No academic paper specifically on optimal Kelly sizing under correlated binary event portfolios on Kalshi or Polymarket was found. The guidance above combines standard theory with vendor write-ups.
- Brier and log-loss benchmarks of the market itself by category (to know how hard each is to beat) are covered by the LLM-forecasting researcher, not here.
