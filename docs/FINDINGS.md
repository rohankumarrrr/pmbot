# Findings

What the data showed while building, as of 2026-11-16. Figures marked *estimate* come from order-book snapshots or simulation, not from money Kalshi has paid.

## 1. Kalshi pays for resting orders, and the pools are large

Source: `GET /incentive_programs` and live order books, scored by the program's own rules (`research/lip_yield.py`, `research/lp_scan.py`).

- 5,826 active liquidity programs paying about **$109,000 a day** in total. Every one uses Target Size 1,000 and discount 0.5.
- 88% of those books met Target Size on both sides at the time of the snapshot, so most pools were paying.
- Pool by category, per day: Entertainment $32,800; Politics $22,800; Financials $19,300; Elections $11,400; Economics $11,400; Science and Technology $4,700; Sports $4,400.
- Adding 100 contracts a side at the best price earns a median of **0.4% a day** on the capital posted, 1.1% at the 75th percentile and 2.3% at the 90th (*estimate*, before fills).
- After the bot's filters, 793 single-side quotes clear 0.5% a day net of expected fill losses. The best 150 would earn about **$138 a day on $1,305 at risk** (*estimate*).

| Price paid | Quotes | Reward per day | Dollars at risk | Median gross yield per day |
|---|---|---|---|---|
| Under 15¢ | 125 | $68 | $616 | 10.4% |
| 15–50¢ | 360 | $261 | $5,067 | 4.9% |
| 50–85¢ | 246 | $165 | $7,146 | 2.1% |
| 85¢ and up | 62 | $32 | $1,829 | 1.6% |

Reasons to distrust the size of these numbers until a live test confirms them:

- They are a snapshot. Other participants can add size at any time, which cuts everyone's share.
- They assume my reading of the rules matches what Kalshi's scoring does.
- The program is scheduled to end 2027-01-01 unless renewed.
- Kalshi describes payouts as "credits"; whether they are withdrawable cash is not confirmed.
- The half of these markets with no trades in a day will, when news arrives, fill resting orders at stale prices.

## 2. Who made money on Kalshi, 2025–2026

Source: a time-random sample of 2,820,864 trades in 359,300 markets (`research/sample_trades.py`, `research/analyze_trades.py`). Returns are dollar-weighted and after fees; standard errors are clustered by event.

| Period | Makers (resting orders) | Takers |
|---|---|---|
| 2025 H1 | +2.6% | −5.7% |
| 2025 H2 | +2.6% | −5.9% |
| 2026 H1 | +1.8% | −5.7% |
| 2026 H2 | +0.5% | −3.6% |

- Makers beat takers in every period, but the maker edge has shrunk by four fifths. November 2026 is the first month in the sample where makers lost (−1.0%, t = −2.5).
- **Price paid matters more than role.** Makers in 2026 non-sports markets:

| Category | Bought under 15¢ | Bought 15–50¢ | Bought 50–85¢ | Bought 85¢ and up |
|---|---|---|---|---|
| Politics | −4% (noisy) | **−45%** | +13% | **+3.6%** |
| Economics | **−98%** | −18% | **+70%** | **+5.6%** |
| Entertainment | −13% (noisy) | −11% | **+17%** | **+2.7%** |
| Commodities | **−53%** | **−21%** | **+13%** | **+3.3%** |
| Weather | **−44%** | −7% | −4% | **+1.5%** |
| Financials | **−46%** | −7% | +2% | +2.0% |

  Bold = more than two standard errors from zero. A resting bid on a cheap contract loses most of its stake when it fills; a resting bid on the favourite makes a little.
- Takers lost most in Elections (−19%), Economics (−15%), Mentions (−11%) and Entertainment (−8%).
- Series that pay liquidity rewards today are thinly traded: only 939 sampled maker fills more than 48 hours from close in May–November 2026. Their maker return is −3% ± 6%, too noisy to call.

## 3. Prices in the bot's categories were biased in 2026

Source: one observation per market per day, 13,945 observations across 5,255 events in Economics, Politics, Elections, Entertainment, Financials, Commodities, Science and Technology.

Fitting `win rate = sigmoid(a + b·logit(price))`:

| Sample | a | b |
|---|---|---|
| 2026, all | −0.17 [−0.24, −0.09] | 1.14 [1.07, 1.20] |
| 2026 H1 | −0.24 [−0.35, −0.12] | 1.15 [1.07, 1.25] |
| 2026 H2 | −0.05 [−0.14, +0.05] | 1.10 [1.02, 1.18] |

`b > 1`: favourites win more often than their price and longshots less. `a < 0`: YES was overpriced. Contracts priced around 43¢ won 37% of the time; around 30¢, 26%; around 20¢, 17%.

The YES overpricing faded in the second half; the slope did not. The bot uses the H2 values (`a = −0.05, b = 1.10`) as its market anchor, and logs a price-only prediction for every universe market so the correction is tested forward at no cost.

## 4. The forecasting pipeline works; whether it is right is unknown

- Seven live events forecast so far, at $0.18–$0.51 each and about three minutes each.
- The research step handled dates and resolution rules correctly in the cases read by hand (TSA weekly throughput; chip-export legislation).
- The model disagreed with the market by 10–25 points in most cases, usually on the low side. That is the direction of the bias in finding 3, and also a known pattern of model overconfidence against liquid prices. Only resolved forecasts will tell which.
- The screen rejected two gas-price events for unclear rules at no measurable cost.

## 5. Shadow run, first half hour

- 60 paper quotes resting, about $250–350 at risk, no fills.
- Estimated rewards $0.79 in 30 minutes, about $38 a day (*estimate*). These quotes were placed before the ranking was corrected for fill losses and lean toward cheap bids.

## 6. Execution on the demo exchange (gate 1, in progress)

- `scripts/gate1_demo_drill.py`: 7 of 7 drills passed on Kalshi's demo exchange on 2026-11-16 (resting order, replay, orphan adoption, cancel-all, kill switch, reset, fill ingestion).
- Kill switch from the command line: `pmbot halt` cancelled all 40 resting orders; the exchange showed none.
- Real crash: the bot was killed with `kill -9` while placing orders. The 11 orders it had been acknowledged for were intact on the exchange; the 12th never arrived and was written off after the 2-minute window. After restart: no duplicate client IDs, no orphans, ledger and exchange matched (`scripts/check_consistency.py`).
- Three bugs the real exchange exposed and the fake one had not: writes without a body are refused; `resume` did not reset the exchange-side order group; Kalshi may cancel orders placed within a minute of a cancel-all. All fixed.
- Kalshi's order listing lags new orders by a few seconds, so a consistency check run immediately after placing can under-count.
- Still to come: the gate asks for two weeks of the loop on demo. It started 2026-11-16 with stand-in reward programs, because demo has none. No fills yet, so fill and settlement handling on a running loop is untested.

## What would change the plan

- A live test in which credited rewards come in far below the estimate, or are not withdrawable.
- Fill rates on resting quotes above roughly 10% a day, which would make cheap bids unprofitable.
- The price-only baseline failing to beat the raw price on a few hundred resolved markets.
- Kalshi not renewing the liquidity program.
