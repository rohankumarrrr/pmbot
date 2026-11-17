# The Reddit post "Prediction Arena: 7 AI agents trade on Polymarket" and live LLM agents trading prediction markets

Research date: 2026-11-16. reddit.com blocked direct fetches. Post and comment text came from the Arctic Shift Reddit archive API (post: https://arctic-shift.photon-reddit.com/api/posts/ids?ids=1qsgh6l ; comments: https://arctic-shift.photon-reddit.com/api/comments/tree?link_id=1qsgh6l ), which returns the original Reddit JSON. Reddit permalinks are cited below.

**Naming collision.** The Reddit post is not the "Prediction Arena" built by Arcada Labs and Harvard (predictionarena.ai / arXiv 2604.07355). It is a solo side project called **Oracle Markets** (oraclemarkets.io). Both are covered below because readers and search results often mix them up.

## Q1. What exactly does the Reddit post describe (builder, models, how agents work, capital, results), and what is "Prediction Arena"?

### Takeaway
The r/algotrading post (2026-01-31) shows a three-week-old **paper-trading** leaderboard from Oracle Markets, a one-person project by u/No_Syrup_4068. Seven mostly open-weight models get €10,000 each in virtual money. Each day they buy YES or NO when their probability differs from Polymarket's by more than 15 points, and they exit the next day. Fees, spreads and slippage are excluded. Returns ranged from −0.2% to +4.1% at the time. By July 2026 the leader was up 14.9%, but about 60% of all profit came from one shared trade (Ukraine ceasefire), and a commenter's cost model turned the whole book negative after fees. The separate, real-money Arcada Labs "Prediction Arena" lost money with every frontier model: −16% to −31% on Kalshi and about −1.1% on average on Polymarket (Jan–Mar 2026). Its site now says it is "paused".

### Cited Findings

**The original post (Oracle Markets "Prediction Arena")**
- Posted 2026-01-31 22:33 UTC to r/algotrading by u/No_Syrup_4068 as an image post with "Strategy" flair. Title: "Prediction Arena - 7 AI Agents trade on polymarket. Here my findings:". In the archive snapshot (~2026-02-02) it had score 10, a 68% upvote ratio, 25 comments and 2 crossposts. — [Reddit post](https://www.reddit.com/r/algotrading/comments/1qsgh6l/prediction_arena_7_ai_agents_trade_on_polymarket/) via [Arctic Shift archive](https://arctic-shift.photon-reddit.com/api/posts/ids?ids=1qsgh6l)
- Post body, quoted: "the idea originated with you, so here is an update on the original divergence board that was planned. If the AI agents' forecast differs from that of Polymarket, they buy Yes or No. It's all very simplified. No trading costs, etc. It's more for testing hypotheses… take it with a pinch of salt." The source link was "Agent Leaderboard | Oracle Markets" (oraclemarkets.lovable.app/leaderboard, which now redirects to oraclemarkets.io/leaderboard). — [Reddit post](https://www.reddit.com/r/algotrading/comments/1qsgh6l/prediction_arena_7_ai_agents_trade_on_polymarket/)
- The leaderboard image is headed "Paper Trading Performance — AI agents vs Polymarket: Exploiting emotional mispricing with €10,000 starting capital." Standings as of 2026-01-31:

  | Rank | Agent | Return | Value | Trades |
  |---|---|---|---|---|
  | 1 | Mystery-rf:v1 | +4.1% | €10,413 | 32 |
  | 2 | Deepseek-v3.1:671b | +4.0% | €10,401 | 20 |
  | 3 | GPT-oss:120b | +3.0% | €10,305 | 51 |
  | 4 | Mistral-large-3:675b | +1.8% | €10,179 | 5 |
  | 5 | Minimax-m2 | +0.7% | €10,072 | 94 |
  | 6 | Qwen3:4b | +0.0% | €10,000 | 0 |
  | 7 | Nemotron-3-nano:30b | −0.2% | €9,981 | 49 |

  — [post image](https://i.redd.it/9oht0xophrgg1.png)
- The image's footnote, quoted: "Paper trades enter when agent-specific divergence thresholds are exceeded and exit at next-day after data update… Results exclude fees, spreads, slippage, funding, and taxes. Shorting (instead of buying No) is for simplification allowed." — [post image](https://i.redd.it/9oht0xophrgg1.png)
- Mechanics OP described in the comments:
  - Daily cadence. A divergence above 15% triggers a trade.
  - Agent probability above Polymarket buys YES; below it shorts YES ("simplified").
  - Every position closes daily and reopens if the divergence still exists.
  - Fixed sizing of 2.5% of the portfolio. Each agent outputs a confidence per probability, but it is not used for sizing.
  - Agents receive "related data (e.g. Bloomberg, Reuters, +100 Sources)".
  - OP: "if trading costs considered this would not make sense at all. But for hypothesis testing its OK."

  — [OP comments in thread](https://www.reddit.com/r/algotrading/comments/1qsgh6l/prediction_arena_7_ai_agents_trade_on_polymarket/)
- Market orders are placed once a day after the data refresh. "No fees or slippage considered." Trading is paper only: "no chain, but using real polymarket data." OP said the models are "well calibrated if you really force them to," though overconfidence is a known problem. — [crosspost in r/PredictionsMarkets](https://www.reddit.com/comments/1qsgjqf)
- Stack: React + Tailwind + Vite frontend, a Python backend with some C++. The code is not open source; OP said users might later be able to upload their own agents. On 2026-02-05 OP added Gemini Flash and Kimi 2.5 plus a forum where agents "roast" each other's predictions. OP says he has worked in AI/fintech "for quite some time". — [Reddit thread](https://www.reddit.com/r/algotrading/comments/1qsgh6l/prediction_arena_7_ai_agents_trade_on_polymarket/)
- Further pipeline details OP gave on 2026-03-13:
  - Hybrid setup: smaller models self-hosted, bigger ones in the cloud.
  - "One Call per day per Question", with about 100 questions live.
  - Live paper trading since 2026-01-10. €10,000 per agent, 2.5% per trade, exit next day.
  - OP had run experimental market-making bots on Polymarket in early September 2025.
  - He planned "100€ real money per Agent… early April".

  — [r/algotrading 60-day update](https://www.reddit.com/r/algotrading/comments/1rsj22d/)
- Data layers as of 2026-04-02: web search, 130+ RSS feeds, and GDELT. OP admitted the 15-point threshold was a "gut feeling" with no testing up front. — [r/algotrading 90-day update](https://www.reddit.com/r/algotrading/comments/1sactqj/)
- As of 2026-07-16 the models are open-weight only ("I am just using open weight models"), all agents can use web search, and memory is limited to the agent's own prediction from the previous day. — [r/algotrading July update](https://www.reddit.com/r/algotrading/comments/1uy5328/)
- "Mystery-rf" is probably a text-only Random Forest. On 2026-02-16 OP posted a TF-IDF Random Forest trained on about 90k resolved Polymarket questions, with about 80% accuracy on 15k held-out questions. He said it was "now having this running with paper money and competing with state of the art LLM's as benchmarks." — [r/algotrading RF post](https://www.reddit.com/r/algotrading/comments/1r6ov4x/random_forest_on_100k_polymarket_questions_80/)

**How Oracle Markets results changed over time (all paper, all before costs, all self-reported)**
- 2026-04-02 (90 days, about 800 trades): "MiniMax has continued to generate profits, while the other models have mostly moved sideways." OP said live-trading infrastructure was set up to test "with real money on a small scale, including trading costs." — [r/algotrading](https://www.reddit.com/r/algotrading/comments/1sactqj/)
- 2026-05-06 (more than 1,000 trades):

  | Agent | Return | Value | Trades |
  |---|---|---|---|
  | Minimax-m2 | +8.6% | €10,859 | 365 |
  | Nemotron-3-nano:30b | +5.0% | €10,497 | 218 |
  | Mistral-large-3:675b | +4.1% | €10,407 | 105 |
  | GPT-oss:120b | +3.2% | €10,318 | 114 |
  | Gemini-3-flash-preview | +2.2% | €10,223 | 86 |

  The top trade was Mistral going long "Khamenei out as Supreme Leader" from 3¢ to 6¢ for +€278. OP said the biggest P&L drivers were Oscar and Ukraine-peace bets. — [r/algotrading](https://www.reddit.com/r/algotrading/comments/1t5g16p/)
- 2026-07-16 to 07-21 (about 6–7 months, 10 agents):

  | Agent | Return | Value | Trades |
  |---|---|---|---|
  | MiniMax-M3 | +14.9% | €11,491 | 413 |
  | Nemotron-3-nano 30B | +13.3% | €11,330 | 261 |
  | Gemini-3-flash-preview | +9.0% | €10,900 | 120 |
  | GPT-oss 120B | +8.6% | €10,863 | 144 |
  | GLM-5.1 | +8.1% | €10,809 | 29 |
  | DeepSeek V4 Flash | +7.4% | €10,736 | 124 |
  | Gemma4 31B | +5.9% | €10,590 | 29 |
  | Mistral Large 3 675B | +5.2% | €10,518 | 163 |
  | Kimi K2.6 | +2.9% | €10,291 | 52 |
  | Qwen3.5 397B | +0.2% | €10,023 | 33 |

  OP's caveat: several agents bought "official Ukraine ceasefire" at about 28¢, which resolved at $1 for roughly €620–€674 per agent. He planned to add drawdowns, risk-adjusted returns and an ex-ceasefire view. — [r/algotrading](https://www.reddit.com/r/algotrading/comments/1uy5328/); [r/LLM](https://www.reddit.com/r/LLM/comments/1v2cfzv/); [r/Polymarket_news](https://www.reddit.com/r/Polymarket_news/comments/1v2cjey/)
- OP's own null result, 2026-09-30: 391,850 news articles across 54 Polymarket markets and 1,888 day-pairs (Jul 15–Sep 30). The correlation between news volume and next-day price move was r = −0.002, "basically zero signal." — [r/algotrading](https://www.reddit.com/r/algotrading/comments/1wujh7m/391850_news_articles_vs_polymarket_basically_zero/)
- Site state on 2026-11-16:
  - The leaderboard page says it shows "Accuracy, Brier scores and simulated trading returns of 10 frontier AI agents." Current agents: kimi-k3, deepseek-v4-pro, glm-5.3, mistral-large-4, minimax-m3.1-flash, gpt-oss:120b, nemotron-3-super, claude-haiku-4-5, gpt-6-luna, gemma4:31b.
  - Headline accuracy: 79.6% for "Oracle Consensus" over 434 resolved markets, Brier 0.166. Nine models are marked retired.
  - Footer: "Scientific forecasting platform. No monetary trading."
  - Current per-agent trading returns sit in a JavaScript-rendered tab and could not be retrieved.

  — [Oracle Markets leaderboard](https://oraclemarkets.io/leaderboard); [Oracle Markets research page](https://oraclemarkets.io/research)

**The other "Prediction Arena" (Arcada Labs / Harvard, real money)**
- Authors: Jaden Zhang and Gardenia Liu (Arcada Labs; Harvard), with Oliver Johansson, Hileamlak Yitayew, Kamryn Ohly and Grace Li (Arcada Labs). arXiv 2604.07355, dated 2026-03-28. — [arXiv HTML](https://arxiv.org/html/2604.07355v1)
- Cohort 1 used **real capital**, $10,000 per model: grok-4-20-checkpoint, claude-opus-4-5, glm-4.7, gpt-5.2, gemini-3-pro-preview and grok-4-1-fast-reasoning.
  - Kalshi ran Jan 12–Mar 9, 2026 (57 days) on 29 curated market series in 7 categories.
  - Polymarket ran Feb 9–Mar 9, with agents free to discover markets across the whole exchange.
  - Cohort 2 (gpt-5.4, claude-opus-4-6, glm-5, gemini-3.1-pro-preview) was **paper trading for 3 days**, Mar 6–9.

  — [arXiv HTML](https://arxiv.org/html/2604.07355v1)
- Agent design:
  - One standard system prompt for all models, with an 8-step decision process that includes expected-value checks.
  - Trading cycles every ~15–45 minutes. Each cycle the agent sees prices and spreads, portfolio state, recent settlements, closed trades, and a "learning" summary of winning and losing patterns.
  - Tools: trade execution, web search, and a notes store. Polymarket adds market-discovery and belief/planning tools.
  - Position limit of 15% of account value per market. Solvency checks include fees. Positions are marked at the bid.

  — [arXiv HTML](https://arxiv.org/html/2604.07355v1)
- Cohort 1 Kalshi results (full period, 2,916 trades): glm-4.7 −16.0% ($8,398); grok-4-20 −20.0%; gpt-5.2 −20.5%; claude-opus-4-5 −25.9% (886 trades, the most); gemini-3-pro −30.5%; grok-4-1-fast −30.8%. Every model lost money. — [arXiv HTML](https://arxiv.org/html/2604.07355v1)
- Cohort 1 Polymarket results (1 month, real money): grok-4-20 −1.85% (18 trades, 71.4% win rate); gemini-3-pro −1.81% (155 trades, 14.3% win rate); gpt-5.2 −0.42% (127 trades); glm-4.7 −0.09% (95 trades); claude-opus-4-5 −2.68% (86 trades); grok-4-1-fast 0 trades. The average was −1.1%, against −22.6% on Kalshi over the same window. — [arXiv HTML](https://arxiv.org/html/2604.07355v1)
- Cohort 2 (paper, 3 days): gemini-3.1-pro +6.02% on Polymarket (76 trades) and claude-opus-4-6 −10.06% on Polymarket. The authors say this is too short to support conclusions, and that paper fills are always filled while live orders can go unfilled. — [arXiv HTML](https://arxiv.org/html/2604.07355v1)
- The authors' explanations:
  - Initial prediction accuracy is the strongest driver. Research volume and token use show no correlation with performance.
  - Weather markets made up 71–97% of each model's Kalshi settlements, so Kalshi results mostly measured weather forecasting.
  - Models cut winners early while holding losers to settlement.
  - Correlated positions settled in the same session: grok-4-20 fell 8.99% on Feb 11 after peaking at +15.5% on Feb 6.
  - Heavy trading without accuracy hurt: Gemini's 664 Kalshi trades went with a near-monotonic decline.

  — [arXiv HTML](https://arxiv.org/html/2604.07355v1)
- On 2026-11-16 predictionarena.ai shows an empty leaderboard with columns for cash, account value, P&L, return, Sharpe, max win, max loss and trades. It reads "Prediction arena is paused — next steps coming soon." It is branded "The Intelligence Company" with an Arcada Labs logo. No wallet addresses are published. — [predictionarena.ai](https://www.predictionarena.ai/)

### Inferences
- The Reddit post is an early (three-week), frictionless, next-day-exit paper experiment. Its headline returns (+4% at best in January, +15% at best by July) measure whether Polymarket prices moved toward the model's view within about 24 hours. They do not measure deployable P&L.
- "Mystery-rf" topping the January board (a text-only Random Forest, not an LLM) suggests the LLMs' early edge over a trivial baseline was nil.
- The 79.6% headline accuracy should not impress. OP's own Random Forest got about 80% from question wording alone, and a commenter noted the market itself is roughly 80% "accurate", so accuracy without beating the price says nothing about edge.
- I found no evidence that the planned €100-per-agent real-money test (spring 2026) ever happened publicly. The November 2026 footer ("No monetary trading") suggests the project moved toward forecasting and analytics instead.
- Treat model rankings from both "arenas" as noise. Oracle Markets' order flipped between January (DeepSeek and the Random Forest on top, MiniMax near the bottom) and May–July (MiniMax on top). Arcada's Grok had the best settlement accuracy yet still lost 20% on Kalshi.

### Gaps
- Current (November 2026) Oracle Markets per-agent trading returns could not be retrieved because the "Investing" tab is client-side rendered. The latest public figures are from 2026-07-16 to 07-21.
- No confirmation of the identity of "Mystery-rf:v1" beyond the inference above.
- The text of the 60-day (2026-03-13) leaderboard images was not available; only commenters' descriptions of them were.
- Whether Arcada's Prediction Arena will resume, or why it paused, is not stated anywhere I found.
- No on-chain verification exists for Oracle Markets, which is paper only, or for Arcada, which published no wallets.

## Q2. What did experienced r/algotrading commenters say?

### Takeaway
The most informative comments agreed on these points:
- **Costs erase the edge.** A commenter rebuilt the July book from the public trade log: it is about −€5.5 to −€7 per trade after Polymarket taker fees and spread.
- **Effective sample size is tiny.** One correlated Ukraine bet supplied about 60% of profit.
- **Next-day exits measure market timing, not forecasting.** Commenters said to score Brier on divergence cases and hold to resolution.
- **The 15-point threshold picks illiquid, penny-priced markets** where paper fills are least realistic.
- **Backtesting LLMs is contaminated** by training data, so only forward tests count.

### Cited Findings

**Original thread (2026-01-31 to 02-05)**
- u/Celac242 (score −3): "These returns are bad… You can put money in HYSA and it's better." OP (+10): "its just one month… Show me the high yield with ~3% return per month?" — [thread](https://www.reddit.com/r/algotrading/comments/1qsgh6l/prediction_arena_7_ai_agents_trade_on_polymarket/)
- u/epidco: "backtesting on paper is fun but polymarket fees and slippage usually eat these tiny margins alive… taking it to prod is a whole different beast." He also cited execution latency. OP agreed that fees, slippage, funding and taxes "could change the game" and said he wants a much longer record than one month. — [thread](https://www.reddit.com/r/algotrading/comments/1qsgh6l/prediction_arena_7_ai_agents_trade_on_polymarket/)
- u/SeaMenCaptain asked what counts as a "day" on a 24/7 market, why positions close daily regardless of direction, and whether confidence could drive sizing. OP: fixed 2.5%, and with costs daily churn "would not make sense at all." — [thread](https://www.reddit.com/r/algotrading/comments/1qsgh6l/prediction_arena_7_ai_agents_trade_on_polymarket/)
- u/arbitrageME: to test "one AI is better than another," go long the winner and short the loser to "isolate your specific idea… pure alpha without exposure to the market level." — [thread](https://www.reddit.com/r/algotrading/comments/1qsgh6l/prediction_arena_7_ai_agents_trade_on_polymarket/)
- u/FutureConsistent8078 said he had seen a correlation between size and return or hit ratio. The rest of the thread was mostly stack questions and a promo for wavestreamer.ai. — [thread](https://www.reddit.com/r/algotrading/comments/1qsgh6l/prediction_arena_7_ai_agents_trade_on_polymarket/)

**60-day update thread (2026-03-13; score 60, 45 comments)**
- u/StratReceipt (+9):
  - Most gains came in the last 7–10 days of the 60-day window, with equity curves "essentially flat noise" before that. This makes a lucky streak on a few correlated events hard to rule out.
  - The top trades were penny markets: Khamenei at 3¢ and the Oscar Best Picture market at 1¢. These have "enormous percentage spreads."
  - Advice: when going live, use high-liquidity mid-priced markets and "log actual fill prices vs the price at signal time."

  — [thread](https://www.reddit.com/r/algotrading/comments/1rsj22d/)
- u/Soft_Alarm7799:
  - "The 15% divergence threshold is doing a lot of heavy lifting… selecting for the most inefficient, lowest liquidity markets where paper fills are the most unrealistic."
  - Many mispricings are "information asymmetry", meaning insiders and sharp money, rather than emotional bias.

  — [thread](https://www.reddit.com/r/algotrading/comments/1rsj22d/)
- u/joeycow (+21, top comment): run a small amount of real money and scale slowly. u/MartinEdge42: most Polymarket data providers are "2-5 seconds stale." u/shajurzi: "I did this and got murdered on unmatched trades." u/LividDrummer1956 suggested Kelly sizing and asked which categories work. OP: finance and crypto markets are "very efficient", while society and culture markets (Oscars, Olympics) are "less sharp." — [thread](https://www.reddit.com/r/algotrading/comments/1rsj22d/)
- Hostile comments called it a "vibe coded ad" or "slop-ad". These reflect sub norms on self-promotion more than substance. — [thread](https://www.reddit.com/r/algotrading/comments/1rsj22d/)

**OP's post about Arcada's real-money arena (2026-03-14; score 147)**
- Title: "They nearly all burned the money they gave to the LLMs. The prediction arena is death." OP linked predictionarena.ai ("It's not me its them"). — [thread](https://www.reddit.com/r/algotrading/comments/1rtgsff/)
- Top replies:
  - "A stochastic prediction machine running random guesses and getting random results? Noted." (+105)
  - "Garbage in = garbage out." (+79)
  - LLMs behave like "an average trader", and the average trader loses. (+28)
  - "With transaction fees, spreads, slippages… trading is not zero-sum but negative-sum… random strategies… will consistently lose money."
  - Predicting markets "is not a brainpower problem."

  — [thread](https://www.reddit.com/r/algotrading/comments/1rtgsff/)

**Later updates (April, May, July 2026)**
- 2026-04-02: u/StratReceipt asked whether the 15-point threshold was fixed before the run or tuned along the way, warning that tuning would make the results "partially fitted to the same period being reported." OP: "No big testing upfront. Gut feeling." — [thread](https://www.reddit.com/r/algotrading/comments/1sactqj/)
- 2026-05-06:
  - u/DontDrinkBongWater (+11): "Excluding fees, spreads and slippage a monkey buying randomly is going to perform well."
  - u/BottleInevitable7278: about 0.02% per average trade is "razor thin."
  - u/MartinEdge42: AI agents' average gross edge on Polymarket is "30-80bps… roughly fee neutral after the new poly v2 fees". Leaderboards should require at least 200 trades per agent; Gemini's 9 trades are "meaningless."

  — [thread](https://www.reddit.com/r/algotrading/comments/1t5g16p/)
- 2026-07-16 (score 48, 30 comments), u/Manuel_SH (+12), quantitative teardown from the public leaderboard:
  - 1,368 settled trades produced a gross €7,510.62 (€5.49 per trade). The Ukraine trade alone was €4,472.63, about 60%. Without it the result is €2.23 per trade.
  - Polymarket's published taker-fee formula, applied to entry and exit with historical fee dates, gives about €7,740.09 (€5.66 per trade). That leaves −€0.17 per trade before spread.
  - The median full spread across 466 of the top 500 markets was 0.2¢. Including it: −€7,587.11, or −€5.55 per trade. Adding 0.25% price impact per leg: about −€6.84 per trade.
  - OP asked for the code, saying the spread cost "seems surprisingly high."

  — [thread](https://www.reddit.com/r/algotrading/comments/1uy5328/); fee sources he cited: [Polymarket fees docs](https://docs.polymarket.com/trading/fees)
- u/AusChicago:
  - "None of the return metrics." With shared positions, "your effective sample size is the number of independent market events, not the number of trades… your leaderboard was mostly ranking one correlated bet."
  - Score Brier on divergence cases specifically. "Next-day exits test whether the market converges to the agent's view within 24 hours, which is a market timing skill, not forecasting." Hold to resolution.
  - "Bootstrap your leaderboard by resampling market events, not trades. I suspect the rank order isn't stable."

  — [thread](https://www.reddit.com/r/algotrading/comments/1uy5328/)
- u/jnwatson (+19): there are too many free variables (tools, memory), and "each model's knowledge cut-off date will be a dominating component." u/Fun-Lingonberry-58: "You cannot backtest something like this because llms already know the outcome of historical events." One workaround is to use an older model only on events after its training cutoff. u/Kev_Edits: frictionless paper trading is "testing aerodynamics in a vacuum." — [thread](https://www.reddit.com/r/algotrading/comments/1uy5328/)
- Several replies in these threads read as LLM-generated, and other users said so ("Bots talking to bots", "Are any of you even real"). — [thread](https://www.reddit.com/r/algotrading/comments/1uy5328/)
- On the Random Forest post (2026-02-16), the top comment (+41) was: "what was the average price of the correct prediction at the time that it was made? You can be 80% accurate and lose money." Others pointed to class imbalance and base rates: "always bet on higher cost option." — [thread](https://www.reddit.com/r/algotrading/comments/1r6ov4x/random_forest_on_100k_polymarket_questions_80/)

### Inferences
- The best critiques form a usable evaluation checklist:
  - Charge real taker fees and spread per leg.
  - Count independent events, not trades.
  - Report results with and without the biggest shared trade.
  - Use Brier or log loss against the market price on divergence cases.
  - Hold to resolution, or report both exit rules.
  - Fix thresholds before the run.
  - Bootstrap rankings over events.
  - Log signal price against fill price when going live.
- Commenters disagreed on whether LLMs have any edge. Optimists pointed to narrative-driven, low-liquidity culture and politics markets. Skeptics argued that apparent mispricings are often informed flow. Both sides agreed that no edge can be judged without costs.

### Gaps
- OP never published code or the cost-adjusted re-run he promised (drawdowns, ex-ceasefire results) in any thread I found.
- Nobody independently replicated Manuel_SH's spread calculation, and OP disputed it.

## Q3. What comparable live AI-trading arenas and experiments exist, and what were their real results?

### Takeaway
Across every public live or paper experiment I found, **no LLM agent has a verified, cost-adjusted, statistically meaningful profit on prediction markets.**
- **Rigorous real-money tests lost money.** Arcada's Prediction Arena, the Kalshi bot maintainer's own audit, and a $23 live bot all lost.
- **Positive results are short, small, or self-reported.** These include PredIQt's 17-day $100 season, Olas' "376% peak trade", Oracle Markets' frictionless paper returns, and DayTrading.com's paper test.
- **The viral wins are unverified marketing**, such as "Claude +1,322% in 48h" and "$50→$3,000".
- The best-known adjacent arena, Nof1 Alpha Arena (crypto and stocks, not prediction markets), showed the same pattern: most frontier models lost, and the winner changed between seasons.

### Cited Findings

**Multi-model arenas on prediction markets**
- **Arcada Labs Prediction Arena (Jan–Mar 2026, real money, $10k per model).** All six models lost on Kalshi (−16% to −30.8%) and averaged −1.1% on Polymarket over one month. Full details are in Q1. The site was paused as of 2026-11-16. — [arXiv](https://arxiv.org/html/2604.07355v1); [predictionarena.ai](https://www.predictionarena.ai/)
- **Oracle Markets (Jan 2026 onward, paper, €10k per agent, open-weight models).** +0.2% to +14.9% gross by July 2026 with next-day exits and no costs. A commenter's fee and spread model makes it about −€5.5 to −€7 per trade. Details in Q1 and Q2. — [r/algotrading](https://www.reddit.com/r/algotrading/comments/1uy5328/)
- **PredIQt (IQ AI), Season 1 (17 days, results announced 2026-01-08, on Polymarket).** Claude-based "Kassandra" +29% (iq.wiki: 28.64%); Gemini-based "KairoStrats" +12%; GPT-5.1-based "Cerebrate/Celebrate Prime" −19%, the only loser. One iq.wiki revision says each agent started with **$100**, and another revision says KairoStrats lost, which conflicts. The source is a press release with no independent verification found. — [Barchart / press release](https://www.barchart.com/story/news/36952826/prediqt-launches-first-arena-for-ai-swarms-to-compete-in-prediction-markets-claude-beats-gemini-and-gpt); [iq.wiki PredIQt](https://iq.wiki/wiki/prediqt)
- **UnifAI "PolyArena" (launched about 2025-10-27).** Six frontier models plus UnifAI's own "UniQ" strategist, each with $1,000 to trade on Polymarket. I found no final standings. A Polymarket market asked whether Claude Sonnet 4.5 would pass Grok 4 on the PolyArena chart by 2025-11-15 ($145K volume), which implies Grok was ahead at some point. UnifAI also ran a 60,000 UAI agent-trading contest in December 2025. — [UnifAI on X](https://x.com/UnifaiNetwork/status/1982757776154820618); [struct.to market page](https://explorer.struct.to/markets/will-claude-pass-grok-by-november-15-on-the-unifai-polyarena)
- **Pieverse "Purr-Fect Agents" Prediction Market Arena (launched 2025-12-22).** GPT-5.2, Claude Sonnet 4.5, DeepSeek v3.2, Gemini 2.5 Pro, Kimi K2 0905 and Grok 4.1, each with $1,000, trading autonomously on Polymarket "on-chain without human intervention." The Medium launch post (seen only as a search snippet; the page returned 403) says USDC on Polygon with the same prompt and execution rules for every model. I found no results or wallet list. — [KuCoin news flash](https://www.kucoin.com/news/flash/pieverse-launches-first-multi-llm-prediction-market-arena-on-polymarket); [Pieverse Medium](https://medium.com/@pieverse/purr-fect-agents-launch-prediction-market-arena-8d101def9510)
- **DayTrading.com Kalshi midterms test (Nov 2026, paper, $10k virtual per model).** The models were labelled GPT-6 Astra, Gemini 4 Argon, Grok 4.7 and Claude Opus 5.5. Grok finished 1st, Claude 2nd (given as a range because Alaska Senate was unresolved), and Gemini and GPT lost money.
  - About 97.5% of Grok's profit was already in its initial picks.
  - "Not one adjusted their bets as results came in."
  - A headline says the average loss was up to 16%, which I could not reconcile with the per-model results.
  - The analyst concluded the results do not justify relying on these models for betting decisions.
  - This is secondhand through Action Network; I could not reach the original report.

  — [Action Network](https://www.actionnetwork.com/news/ai-chatbot-election-predictions)

**Adjacent arena (not prediction markets): Nof1 Alpha Arena**
- Season 1 ran Oct 17/18 to Nov 3, 2025, with $10k of real money per model trading crypto perpetuals on Hyperliquid.
  - Qwen3 Max won with about +22% (about $12,231). DeepSeek V3.1 ended at about $10,489. Claude Sonnet 4.5 ended at about $5,799.
  - GPT-5 lost about 60–63%. Sources differ: 62.7% vs. 63%.
  - Gemini 2.5 Pro and Grok 4 also lost money.

  — [Forklog](https://forklog.com/en/four-out-of-six-ai-models-suffer-losses-in-trading-tournament/); [GN Crypto](https://www.gncrypto.news/news/qwen-wins-alpha-arena-season-1-with-22-percent-returns/)
- Season 1.5 ran Nov 19 to Dec 3, 2025 on US stock tokens on Hyperliquid, in four modes. A "Mystery Model", reported as Grok 4.20 but not officially confirmed, won with +12.11% aggregate. GPT-5.1 was 2nd and Gemini 3 was 3rd. — [Powerdrill summary](https://powerdrill.ai/blog/alpha-arena-season); [Forklog](https://forklog.com/en/ai-model-grok-4-2-triumphs-in-trading-tournament/amp)
- Note: these Alpha Arena figures come from secondary crypto-media summaries surfaced by search, not from Nof1's own leaderboard (nof1.ai/leaderboard).

**Autonomous agent products**
- **Olas Polystrat (Polymarket) and Omenstrat (Omen on Gnosis).**
  - Polystrat launched in February 2026 on the Pearl app store and trades Polymarket around the clock for users.
  - Olas' Q1 2026 roundup reports about 14,700 Polystrat trades across about 1,750 markets. A DEV.to post claims about 4,200 trades in the first month with a "peak single-position return +376%".
  - In a crypto.news interview, an Olas executive (Minarsch) put Polystrat accuracy at 56–69%.
  - Omenstrat has traded Omen markets since July 2023 with more than 14M transactions. Olas' Q4 2025 roundup highlights one trader agent (#2268) with an 85% month-to-date ROI and "up to ~74% accuracy" for selected agents.
  - These are all self-reported activity counts or cherry-picked figures. No fleet-level net ROI was found. One aggregator's "18.9% average ROI" could not be traced to an Olas source.

  — [Olas Polystrat launch](https://olas.network/blog/introducing-polystrat-an-autonomous-ai-prediction-agent-on-polymarket); [Olas Q1 2026 roundup](https://olas.network/blog/olas-q1-2026-roundup); [Olas Q4 2025 roundup](https://olas.network/blog/q-4-25); [crypto.news](https://crypto.news/pearl-prediction-markets-and-the-long-tail-of-ai-liquidity/); [DEV.to](https://dev.to/fatherson/ai-agents-are-now-autonomously-trading-on-polymarket-and-beating-humans-45d5); [Olas Agent Explorer](https://olas.network/blog/agent-explorer)
- **Polymarket's official "Agents" framework.**
  - MIT-licensed developer toolkit: an OpenAI-based LLM, RAG with Chroma, news and search connectors, the Gamma API client, and CLOB order signing and execution.
  - It makes no performance claims.
  - It was archived on 2026-05-11 (3.8k stars, 830 forks, 7 commits).

  — [GitHub Polymarket/agents](https://github.com/Polymarket/agents)

**Individual builders' write-ups**
- **ryanfrigo/kalshi-ai-trading-bot** (Kalshi, real money):
  - The latest published verdict, dated 2026-10-02 from the operator's live account, is "NO MEASURED EDGE": won 58% vs. 60% implied by the book (edge −1.9 points), Brier 0.2356.
  - The README says: "Running this with real money historically led to significant losses on this repo."
  - It retracts an earlier "5-model ensemble" claim. Lessons: "The LLM could be 80% confident on a CPI trade and still be wrong"; "at a 45% win rate, three-quarter Kelly compounds losses catastrophically"; "More trades without edge is faster path to zero."

  — [GitHub README](https://github.com/ryanfrigo/kalshi-ai-trading-bot)
- **Andy Hall, "Free Systems" Substack (2026-01-06), Kalshi, small real stake.**
  - Pipeline: Claude Haiku for triage, Sonnet 4.5 and Opus 4.5 for analysis, GDELT news, and a "council" debate among GPT-5.2, Gemini and Grok-4. About 675 contracts were screened.
  - One closed trade: bought No at 50¢, sold above 80¢ (+60%). No aggregate P&L.
  - Failure modes:
    - Time confusion: the agent gave a 52.9% probability to Republicans winning the House against a 20% market price, reasoning as if the election had already happened.
    - Incoherent probabilities across mutually exclusive outcomes.
    - Overconfidence.
    - Cost: running Opus on every contract "could cost thousands of dollars a month."
  - He notes, "One trade proves nothing."

  — [Free Systems](https://freesystems.substack.com/p/can-ai-reason-about-politics-i-built)
- **Whirligig Bear / Kalshinomics (2025-11-18).** About $20k of real Kalshi bets on obscure Grammy categories priced by "ChatGPT Thinking… like a Superforecaster," with estimated EV of $1–2k. The author benefits from Kalshi referrals and says he was "talking my book." No outcome was reported in the version fetched. — [Whirligig Bear](https://whirligigbear.substack.com/p/chatgpt-20k-grammys)
- **Startup Fortune "I actually gave an AI money to trade on Polymarket"** (page shows 2026-02-12; a search listing showed Jul 14, 2026).
  - About $23 of real USDC. About 46 hours live and about 140 trades (13 wins and 24 losses reported). The balance fell to about $1.50 (about −93%) before a kill switch.
  - Main cause: tokens bought in neg-risk and multi-outcome markets could not be sold, producing more than 8,500 failed exit attempts. The bot also re-entered the same BTC up/down market 8 times and duplicated orders after a restart.
  - The author also debunks the "$50→~$3,000 in 48h" viral claim, which came from a five-month-old account linking a Polymarket referral.

  — [Startup Fortune](https://startupfortune.com/i-actually-gave-an-ai-money-to-trade-on-polymarket-heres-what-nobody-on-twitter-wants-you-to-know/)
- **Leo Labs Polymarket "strategy graveyard"** (about 3 months, mostly real but small capital): 25 directions tested, 4 survived, with "spare change" returns.
  - The only AI strategy, LLM-judged news-event trading, was shelved because the pipeline was too slow.
  - Settlement harvesting went 13-0 and still lost money: profit was under 3¢ per trade against a 2% taker fee.
  - BTC daily direction: 5,036 trades, 52.6% win rate, p = 0.072, not significant.
  - Survivors: weather markets at about break-even, crypto up/down, and niche categories with "weak opposition."

  — [Leo Labs](https://leolabs.me/blog/pm-strategy-graveyard/en/)
- Other small self-reports, seen only as search snippets and not fetched:
  - A Claude-built Kalshi bot won 8 of 12 trades and was still about $7 down. — [Built This Week](https://www.builtthisweek.com/builds/kalshi-prediction-market-trading-bot)
  - An "AI-augmented" Polymarket 5-minute BTC bot: 522× in simulation vs. −49.5% live. — [Medium](https://medium.com/@gwrx2005/ai-augmented-arbitrage-in-short-duration-prediction-markets-live-trading-analysis-of-polymarkets-8ce1b8c5f362)
  - A 90–95¢ favorite-buying bot (Mar 19 to Jun 10, 2026, about $100) "won 93% of its bets and still lost money." — [GitHub Hash-Trail](https://github.com/Hash-Trail/polymarket-bot)

**Viral or hype claims (unverified)**
- "Claude +1,322% ($1,000→$14,216) in 48h on Polymarket while an OpenClaw agent was liquidated" (2026-03-10, from an X post by @TFTC21 with more than 1.2M views). There are no wallet addresses and no strategy, sizing or risk disclosure. KuCoin's write-up notes it relies on the viral post. — [KuCoin / Finbold](https://www.kucoin.com/news/flash/claude-ai-agent-generates-1-322-return-on-1-000-in-48-hours-on-polymarket)

**Context and base rates**
- CryptoSlate (2026-07-22, updated 2026-08-17):
  - Foresight Arena estimates that detecting a 2-point edge takes about 350 resolved binary predictions, and a 1-point edge about 4× as many.
  - A working paper (arXiv 2607.06166) finds forecast accuracy turns into profit only with proper betting strategy and enough liquidity.
  - Prop firm Propr plans Polymarket evaluations and A-books only about 5% of signals.

  — [CryptoSlate](https://cryptoslate.com/easy-money-on-polymarket-and-kalshi-is-disappearing-as-prop-firms-deploy-ai-agents/)
- An on-chain study covered by The Defiant (April 2026) reports that only about 2% of 2.5M Polymarket wallets ever made more than $1,000. This comes from a search summary and was not fetched. — [The Defiant](https://thedefiant.io/news/research-and-opinion/polymarket-profitability-report-april-2026)

### Inferences
- The evidence ladder from strongest to weakest:
  1. Real money, multi-week, multiple models, published method: Arcada. Result: losses.
  2. Real money from individual operators who audit themselves: ryanfrigo, Startup Fortune, Leo Labs. Result: losses or no measurable edge.
  3. Short real-money vendor arenas: PredIQt ($100, 17 days), PolyArena and Pieverse (no results found). Results are positive but tiny-sample and self-reported.
  4. Paper tests: Oracle Markets, DayTrading.com, Arcada's Cohort 2. Positive before costs.
  5. Viral social claims. Unverified.

  Positive results show up almost exclusively at the weak end.
- The only structural edge the evidence hints at is market selection. Polymarket's open discovery beat Kalshi's curated weather-heavy set in Arcada's test, and builders report better pricing in niche, low-liquidity culture and politics markets. But those are the markets where spread, impact and capacity constraints are worst, so any edge is likely small and capacity-limited.
- Vendor arenas (PredIQt, UnifAI, Pieverse, Olas) double as token or product marketing. None published per-agent wallet addresses that I could find, so on-chain verification was not possible.

### Gaps
- No final standings found for UnifAI PolyArena or the Pieverse arena, and no wallet addresses for either.
- No independent, fleet-level net ROI for Olas Polystrat. The Hugging Face trader dashboard (https://valory-trader-agents-performance.hf.space/) covers Omen-side traders and was not inspected.
- Final P&L for the Whirligig Bear Grammy bets (resolved February 2026) was not found.
- Fast Company's "AI traders are already testing prediction markets—and losing money", the Cybernews debunk, and the Level Up "Seven AI models traded prediction markets for a week, five lost money" piece all returned 403 or were paywalled. Their specific figures are not included.
- Whether Nof1 ran a 2026 season, or any prediction-market season, was not checked.
- Manifold or Metaculus bot tournaments that also trade were not found in this pass, and academic benchmarks such as Prophet Arena and Foresight Arena were deliberately left out of scope.

## Q4. Is there independent verification for these results?

### Takeaway
Almost none. Arcada published trade counts and a methodology but no wallets. Oracle Markets publishes a trade log on its site (enough for a commenter to recompute P&L), but it is paper. Olas' activity is on-chain, yet its ROI claims are self-reported and cherry-picked. Vendor arenas and viral posts give no wallet addresses.

### Cited Findings
- Arcada Prediction Arena gives no wallet addresses and no on-chain verification in the paper, and the site's leaderboard is empty or paused. — [arXiv](https://arxiv.org/html/2604.07355v1); [predictionarena.ai](https://www.predictionarena.ai/)
- Oracle Markets is paper only ("no chain"). Its public leaderboard exposes individual trades: Manuel_SH "pulled the 1,368 settled trades from the Oracle Markets leaderboard." — [r/PredictionsMarkets crosspost](https://www.reddit.com/comments/1qsgjqf); [r/algotrading](https://www.reddit.com/r/algotrading/comments/1uy5328/)
- Olas' Agent Economy Explorer tracks on-chain activity (transactions, daily active agents), not profit. Polystrat's per-agent performance is visible only inside the Pearl app. — [Olas Agent Explorer](https://olas.network/blog/agent-explorer); [Olas Polystrat launch](https://olas.network/blog/introducing-polystrat-an-autonomous-ai-prediction-agent-on-polymarket)
- The "Claude +1,322%" claim comes with no wallet or transaction links. — [KuCoin / Finbold](https://www.kucoin.com/news/flash/claude-ai-agent-generates-1-322-return-on-1-000-in-48-hours-on-polymarket)
- ryanfrigo's Kalshi bot publishes its verdict, but "settlements aren't committed, so the figures can't be re-run." Kalshi is not on-chain anyway. — [GitHub README](https://github.com/ryanfrigo/kalshi-ai-trading-bot)

### Inferences
- Anyone building a credible track record should publish Polymarket proxy-wallet addresses, or Kalshi statements, plus a trade ledger with signal-time and fill prices. No project reviewed here does all of these.

### Gaps
- No Dune dashboard tracking a named LLM-agent wallet was found.

## Q5. What lessons recur across post-mortems?

### Takeaway
The same failure modes appear in every source:
1. Fee and spread drag swamps thin gross edges.
2. Win rate is not profitability (buying favorites, settlement harvesting).
3. Tiny or correlated samples (a single event drives the leaderboard).
4. Illiquid or penny markets where paper fills are fiction.
5. Overconfidence and miscalibration. Time and resolution misreads.
6. Look-ahead or training-data leakage makes backtests useless.
7. News latency: the market prices news first.
8. Operational bugs (unsellable tokens, duplicate orders, stale data) and paper-vs-live execution gaps.
9. Exit discipline: models cut winners and hold losers.

### Cited Findings
- **Fees and spread.** Oracle Markets goes from +€5.49 per trade gross to about −€5.5 to −€7 per trade with taker fees and a 0.2¢ spread. — [r/algotrading](https://www.reddit.com/r/algotrading/comments/1uy5328/). A 2% taker fee wiped out near-certain trades. — [Leo Labs](https://leolabs.me/blog/pm-strategy-graveyard/en/). Average gross edge of 30–80 bps is "roughly fee neutral after the new poly v2 fees." — [r/algotrading](https://www.reddit.com/r/algotrading/comments/1t5g16p/)
- **Win rate is not profit.** 13-0 settlement harvesting still lost money. — [Leo Labs](https://leolabs.me/blog/pm-strategy-graveyard/en/). "You can be 80% accurate and lose money." — [r/algotrading](https://www.reddit.com/r/algotrading/comments/1r6ov4x/random_forest_on_100k_polymarket_questions_80/). Arcada's grok-4-20 had a 71.4% Polymarket win rate and still lost 1.85%. — [arXiv](https://arxiv.org/html/2604.07355v1)
- **Correlation and sample size.** One Ukraine ceasefire trade supplied about 60% of Oracle Markets' profit. — [r/algotrading](https://www.reddit.com/r/algotrading/comments/1uy5328/). Correlated same-session settlements cost grok-4-20 8.99% in one day. — [arXiv](https://arxiv.org/html/2604.07355v1). About 350 resolved predictions are needed to detect a 2-point edge. — [CryptoSlate](https://cryptoslate.com/easy-money-on-polymarket-and-kalshi-is-disappearing-as-prop-firms-deploy-ai-agents/)
- **Illiquid and penny markets.** The 15-point divergence filter "select[s] for the most inefficient, lowest liquidity markets where paper fills are the most unrealistic." Top trades were at 1–3¢. — [r/algotrading](https://www.reddit.com/r/algotrading/comments/1rsj22d/)
- **Overconfidence, time confusion and resolution misreads.** Andy Hall's agent treated a future election as already held and produced incoherent probabilities. — [Free Systems](https://freesystems.substack.com/p/can-ai-reason-about-politics-i-built). "The LLM could be 80% confident on a CPI trade and still be wrong." — [GitHub](https://github.com/ryanfrigo/kalshi-ai-trading-bot). Arcada's losses were driven by systematic weather misprediction. — [arXiv](https://arxiv.org/html/2604.07355v1)
- **Look-ahead and leakage.** "You cannot backtest something like this because llms already know the outcome of historical events." — [r/algotrading](https://www.reddit.com/r/algotrading/comments/1uy5328/). OP chose forward paper testing for this reason. — [r/algotrading](https://www.reddit.com/r/algotrading/comments/1rsj22d/)
- **News latency and information.** News volume has r = −0.002 with next-day moves. — [r/algotrading](https://www.reddit.com/r/algotrading/comments/1wujh7m/391850_news_articles_vs_polymarket_basically_zero/). An LLM news-trading pipeline was "too slow." — [Leo Labs](https://leolabs.me/blog/pm-strategy-graveyard/en/). Data feeds are 2–5 seconds stale. — [r/algotrading](https://www.reddit.com/r/algotrading/comments/1rsj22d/). Obvious mispricings often reflect information the bot lacks. — [Startup Fortune](https://startupfortune.com/i-actually-gave-an-ai-money-to-trade-on-polymarket-heres-what-nobody-on-twitter-wants-you-to-know/)
- **Operational and execution gaps.**
  - Unsellable neg-risk tokens, more than 8,500 failed exits, duplicate orders after a restart, and Cloudflare blocking datacenter IPs. — [Startup Fortune](https://startupfortune.com/i-actually-gave-an-ai-money-to-trade-on-polymarket-heres-what-nobody-on-twitter-wants-you-to-know/)
  - Paper fills always execute, while live orders can find no counterparty. — [arXiv](https://arxiv.org/html/2604.07355v1)
  - "Got murdered on unmatched trades." — [r/algotrading](https://www.reddit.com/r/algotrading/comments/1rsj22d/)
- **Exit discipline and overtrading.** Models cut winners early and held losers to settlement. Gemini's 664 Kalshi trades went with a near-monotonic decline. Research and token volume did not correlate with returns. — [arXiv](https://arxiv.org/html/2604.07355v1). "More trades without edge is faster path to zero." — [GitHub](https://github.com/ryanfrigo/kalshi-ai-trading-bot)
- **Sizing.** "At a 45% win rate, three-quarter Kelly compounds losses catastrophically." Use a 20% drawdown cap, not 50%. — [GitHub](https://github.com/ryanfrigo/kalshi-ai-trading-bot)
- **Static agents.** DayTrading.com's models "never revised their bets as results came in." — [Action Network](https://www.actionnetwork.com/news/ai-chatbot-election-predictions)

### Inferences
- The LLM is rarely the binding constraint. Execution realism, cost modelling, market selection and statistical evaluation decide whether a forecasting edge, if one exists, survives. A credible build should be judged on calibration against market price on divergence cases, out of sample, on independent events, with real fills.

### Gaps
- No source quantifies a typical realized slippage distribution for small LLM-agent orders across Polymarket price buckets. Commenters' 0.2¢ median spread and "~33% of profit on penny trades" figures are rough estimates.
