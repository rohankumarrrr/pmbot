# Design

Goal: find out cheaply whether there is a repeatable profit on Kalshi, exploit it in small size if there is, and stop if there is not.

## What changed from the first plan

The first plan had one strategy: an AI forecast blended with the market price, traded with resting limit orders. Building it surfaced four things that changed the plan.

1. **Kalshi pays for resting orders.** Its Liquidity Incentive Program pays a daily pool in about 5,800 markets (about $109,000 a day in total on 2026-11-16) to orders resting near the top of the book. Scoring live books by the program's rules shows rewards of several percent a day on the dollars at risk in many quiet markets. That is larger than any forecasting edge in the research, so reward-aware quoting became the first strategy and the forecaster became the second.
2. **The model runs through the Claude CLI.** No API keys or search subscriptions are needed, and the CLI's built-in web search replaced the planned search providers. The cost is about $0.50 of usage per event.
3. **History can be tested without hindsight problems, but only for price-based rules.** A random sample of 2.8 million Kalshi trades (2025-01 to 2026-11) measures what makers and takers actually earned. Model forecasts still need forward testing, because a model already knows how old events ended.
4. **The trade history changed two rules.** Resting bids on cheap contracts lose most of their stake when filled, so reward quotes are now ranked net of expected fill losses by price. And prices in the bot's categories were biased in 2026 (YES overpriced, favourites underpriced), so the forecast blend anchors on a corrected price, with a free price-only baseline logged for every universe market.

## The cycle

```
every cycle (default 10 min)
  catalog      pull every open event and market; store new ones; snapshot prices
  sync         ingest fills (simulated from the trade tape in shadow mode); record settlements
  risk         drawdown and daily-loss checks; a breach cancels everything and halts
  upkeep       cancel forecast orders whose market moved; re-quote fresh forecasts
  rewards      accrue estimated rewards; cancel quotes that stopped earning; place new ones
  leases       push forward the expiry of every order still wanted
  forecast     up to 2 events: screen -> research + rules check -> 5-model ensemble -> decide
```

All state lives in `data/ledger.sqlite`. A restart at any point is safe: orders are keyed to the decision that produced them, and the exchange is treated as the source of truth for order and fill status.

## Strategy 1: liquidity rewards

Program rules, from Kalshi's CFTC filing and help centre:

- One snapshot a second. It counts only if both sides of the book hold at least Target Size (1,000 contracts today).
- Qualifying bids on a side: walk down from the best bid, taking whole price levels, until Target Size is reached.
- Reference price: the level where cumulative size first reaches a fifth of Target Size.
- An order scores `size × discount^(ticks below the reference)`, and full weight at or above it. The discount is 0.5 today.
- Each side's scores are normalised to 1. Your snapshot score is your share on both sides. Reward = pool × your share of all scores × the fraction of snapshots that counted. Programs pay nothing under $1.
- The program is scheduled to end 2027-01-01 unless Kalshi renews it. It has been renewed before.

What the bot does with them:

- **Where to quote.** At the reference price, not the best price. It earns full weight while standing behind the orders ahead of it.
- **Which quotes.** Rank every eligible (market, side) by net yield: `(reward per day + fill_prob_day × fill_return(price)) ÷ dollars at risk`. `fill_return` is what filled resting orders returned at that price in 2026 (−45% under 15¢, −15% at 15–50¢, +5% at 50–85¢, +2% above). `fill_prob_day` is 25%, the rate the paper run measured on 2026-11-17 (0.22 a day under 15¢, 0.42 at 15–50¢, from 20 simulated fills); it started as an assumed 10%. Take the best until the capital budget or the quote limit is reached.
- **What it avoids.** Sports, crypto and mention markets; markets closing within 48 hours; markets whose price moved more than 8¢ in a day; markets trading more than 2,000 contracts a day; series that charge maker fees. These are where a resting order is most likely to be filled by someone who knows more.
- **Size.** 50 contracts a side, cut down so no quote risks more than $30. At most 60% of the bankroll in quotes and inventory, across at most 120 quotes.
- **Inventory.** A filled side is held to settlement and not re-quoted while the position is full. The other side keeps quoting; if it fills too, the pair locks in the spread.
- **Staying put.** A program pays only if the account's share reaches $1 by the end of its period (1 to 7 days), so rewards are counted per program. A quote is placed only where what is already earned plus what it would add clears $1.50 by the end; new quotes go first to programs already earning; and a quote that can no longer reach $1 is pulled. The first live day spread an estimated $8.85 over 141 markets and none reached the floor.
- **Too close to the answer.** "Closing within 48 hours" is judged by when the outcome is decided (the earlier of the close and the expected expiration), and "price moving" falls back to the previous day's book when nothing traded then. Both gaps cost money live.
- **Refusals.** If the exchange refuses an order because the book moved while it was being placed, that market is not quoted again for 6 hours.
- **Upkeep.** A quote is cancelled when the reference price moves two ticks away (one tick caused constant re-quoting on paper: 79% of cancels, and the hourly order cap was reached), the side drops below Target Size, the market stops being eligible, the price would cross, or its reward no longer covers its expected fill cost.

In shadow mode the reward is an estimate: each cycle the bot scores the live book with its order added, and credits that share of the pool for the time since the last cycle. Fills are simulated from the trade tape with queue position. Only a live test can confirm what Kalshi actually credits.

### Families, and settings changed while running

- **Family cap.** Markets are grouped by the first 8 letters of their series name (`lp.family_prefix_len`), a crude stand-in for "moves on the same news". At most `lp.max_markets_per_family` (3) are quoted or held per family. On 2026-11-20 the live bot was filled in 17 gas-price markets, one per state, on one piece of news.
- **Pause.** `lp.exclude_families` lists ticker prefixes that are not quoted; quotes already resting there are pulled (`family_paused`).
- **Run-time settings** (`overrides.py`). `pmbot set`, `unset`, `pause` and `unpause` store changes to `lp.*` in the bot's ledger; the reward strategy re-reads them at the top of every step. Each change is logged as a `setting_changed` risk event. Hard limits and anything outside `lp` are refused. The intended use is a quick experiment, usually on the twin, that is then either promoted into the config file or unset.

### Offering out filled positions

A filled quote leaves a position that ties up budget until its market settles, which can be months. With `lp.offer_out_positions` on, the bot rests an offer on each position: a bid on the other side for exactly the contracts held, at that side's reference price. A YES and a NO contract in one market pair off into $1, so buying NO at 94c against YES held is selling the YES at 6c. The offer earns the program's reward like any quote. A fill closes the position at the going price and frees the budget.

Such an order (decision kind `lp_close`) puts nothing new at risk, so the per-quote cap, the budget, the payout floor and the yield rule do not apply to it, and it does not count as dollars at risk. It is cancelled the moment it is larger than the position it closes (`position_gone`), so it can never open a position on the other side.

The setting is off by default and is not for the live bot yet. On paper the pairing is the ledger's own arithmetic. On the exchange an offsetting order has to be sent so that it can only reduce a position, and how Kalshi margins it must be checked on the demo exchange first.

## Strategy 2: forecast blend

- **Universe.** Non-sports events priced 15–85¢, spread ≤ 4¢, at least 20 contracts on both sides, closing in 2–60 days. Newer listings first. Politics, elections and financials are forecast and scored but not traded until they prove out.
- **Screen** (Haiku, no web): is this forecastable from public information, and are the rules clear? About 15% of slots skip the screen at random so the screen itself can be evaluated.
- **Research** (Sonnet, web search): a dated fact dossier, a base rate, upcoming events, and a rules check that asks whether the outcome has already been decided. If it has, or the rules are unclear, the event is skipped.
- **Ensemble.** Opus ×2, Sonnet ×2, Haiku ×1 read the same dossier and never see the market price. The median is the model probability; the spread across samples is the uncertainty.
- **Anchor.** The market mid is first corrected for how such prices resolved in 2026: `anchor = sigmoid(a + b·logit(mid))` with `a = −0.05, b = 1.10`.
- **Blend.** `p_final = sigmoid(w·logit(anchor) + (1−w)·logit(p_model))` with `w = 0.67` until refitted on resolved forecasts. Model calibration is the identity until then too.
- **Baseline.** Every universe market gets a price-only prediction (the anchor) logged once a week. It costs nothing, resolves by the hundred, and is the benchmark the model has to beat.
- **Budget.** Up to 12 forecasts in any 24 hours, paced at 2 per 4 hours so they are spread across the day, and one event per series per day. Events the screen or rules check rejects do not use a slot; a daily dollar cap covers everything.
- **Order.** Post-only, one tick inside the spread when there is room, otherwise joining the best price. Sized at 0.2× Kelly, capped at 3% of bankroll per market and 10% per event. Needs at least 3¢ of edge after fees, and more than the ensemble's own disagreement.
- **Staleness.** Prices are re-read after research. An order is pulled if the mid moves more than 3¢ from the decision.

The model never has tools that can place orders. Web content is untrusted, and its only outlet is one probability among five.

## Risk

- Per-market cap 3% of bankroll, per-event cap 10%, counting filled positions plus the unfilled part of resting orders.
- Halt and cancel everything at a 20% drawdown from peak equity or a 5% loss in a day. A halt is cleared only by hand.
- Order writes are never retried automatically. Every order carries a client ID derived from its decision, so a replay cannot double-submit.
- On the exchange, all orders sit in one order group with a rolling contract limit, and are cancelled if trading pauses.
- **Order leases.** Every order is placed to expire 15 to 20 minutes out (`risk.order_lease_minutes`), and each cycle pushes the expiry of the orders it keeps forward, in place, without losing queue position. If the bot, its server or its network stops, the orders lapse on the exchange within one lease. Before this, a stopped bot left reward quotes resting for up to 7 days; on paper, one order was filled 11¢ through the market while the machine slept. Verified on the demo exchange by stopping the bot and watching its orders disappear.
- Positions are valued at the midpoint of the latest book no wider than 10¢, or at cost if there has never been one. A wide book's midpoint is not a price.
- On an exchange, equity is measured from the cash the account began with, so a restart cannot shift it.
- For live trading: a dedicated subaccount holding only the test bankroll, and an API key that can only read and trade inside it (no transfers, no key management). `scripts/setup_subaccount.py` sets both up and can delete the key it was given for the whole account.

## Gates

`config/gates.yaml` holds the thresholds, written before any forecast resolved. In short:

| Gate | Question | Evidence |
|---|---|---|
| 0 | Does the forecast add anything to the price? | 350 resolved events; blended Brier beats the market's on the later half with a 95% interval below zero; simulated profit positive even without the best event |
| 1 | Is execution sound? | Demo exchange: no duplicate or orphaned orders across forced restarts; kill switch verified; ledger matches exchange fills |
| 2 | Does it work with real money? | $250–1,000, 100+ fills over 50+ events; profit after fees ≥ 0; halt at −20% |
| 3 | Scale? | At most 2× a quarter while gate 2 holds |

The reward strategy has its own, shorter path: a few days of shadow estimates, then a small live test, because credited rewards are observable within days and the program has an end date.
