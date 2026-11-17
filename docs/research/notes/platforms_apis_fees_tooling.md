# Prediction Market Trading Agents: Platform Mechanics, APIs, Fees, Data, Tooling, and Architecture (as of 2026-11-16)

Research date: 2026-11-16. Official docs were pulled live (docs.kalshi.com, docs.polymarket.com, docs.polymarket.us, docs.novig.com, docs.manifold.markets, IBKR docs). GitHub stats were pulled live from the GitHub API on 2026-11-16. Third-party summaries are labeled as such.

**Recent changes a builder must know about (all verified in official docs unless noted):**
- **Polymarket US raised taker fees for small accounts on 2026-11-14.** It now uses volume tiers: Θ=0.095 below $10k trailing-30-day taker volume, down to 0.0695 at $250k or more. Before that, third-party guides reported a flat 0.06 taker fee plus a 0.0125 maker rebate from July 1, 2026.
- **Kalshi removed its legacy v1 order-write endpoints.** They now return `410 Gone`, and orders must go through "Create Order (V2)" with fixed-point dollar prices. Kalshi has also added perps, a hosted MCP server, Ed25519 keys, dedicated `external-api` hosts, and a live/historical data split.
- **Polymarket international was re-platformed.** Collateral is now pUSD (a USDC-backed ERC-20). There are unified SDKs (`@polymarket/client`, `polymarket-client`) and "Protocol V2" markets. The old `py-clob-client` and `clob-client` repos are archived. Data API v1 was retired on 2026-11-02 according to a third-party guide, and the docs carry a v1-to-v2 migration guide.
- **The official `Polymarket/agents` AI-agent repo is archived.** Its last push was 2024-11-05.
- **Polymarket international lists the United States as "Close-Only" on both frontend and API.** US residents cannot open new positions there, so Polymarket US is the US route.

---

## Q1. Venues accessible to a US resident in late 2026 and their programmatic access

### Takeaway
For a US individual who wants fully automated, API-driven trading, the realistic venues are **Kalshi** and **Polymarket US**. Kalshi has the most mature API, a free demo environment and the most liquidity. Polymarket US offers a KYC-gated retail REST and WebSocket API with official Python and TypeScript SDKs. Two narrower options exist: **Interactive Brokers ForecastEx** (TWS and Web API, limit orders only, buy-only) and **Novig** (sports only, full trading API). **Manifold** is the play-money sandbox. Robinhood, Crypto.com and PredictIt do not offer individuals a documented order-placement API. Polymarket international is close-only for US IPs.

### Cited Findings

**Kalshi (CFTC DCM): REST, WebSocket and FIX**
- **Hosts:**
  - Production REST: `https://external-api.kalshi.com/trade-api/v2`. The legacy host `api.elections.kalshi.com` still works and serves all markets despite its name.
  - Production WebSocket: `wss://external-api-ws.kalshi.com/trade-api/ws/v2`.
  - Dedicated lower-latency `fill` and `user_orders` WebSocket host: `wss://user-ws.kalshi.com/trade-api/ws/v2`.
  - AWS PrivateLink for Premier tier and above; VPC peering for Prime and above.
  - Source: [Kalshi API Environments](https://docs.kalshi.com/getting_started/api_environments.md)
- **Demo/sandbox:** `https://demo.kalshi.co/` with mock funds. Demo REST is `https://external-api.demo.kalshi.co/trade-api/v2` and demo WebSocket is `wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2`. Credentials are not shared with production. Kalshi warns that "price and behavior of markets in the demo environment may not be reflective of those in real markets." — [Kalshi Demo Env](https://docs.kalshi.com/getting_started/demo_env.md)
- **Auth:** API key plus signed requests. RSA keys work with every SDK version; Ed25519 keys need SDK 3.31.0 or later. You sign the path from the API root without the query string (e.g. `/trade-api/v2/portfolio/orders`). — [Kalshi SDKs](https://docs.kalshi.com/sdks/overview.md); [Kalshi API Environments](https://docs.kalshi.com/getting_started/api_environments.md)
- **Rate-limit tiers** (token buckets, tokens per second). Default cost is 10 tokens per request, so Basic works out to about 20 reads/s and 10 order writes/s.

  | Tier | Read | Write | WebSocket conns |
  |---|---|---|---|
  | Basic | 200 | 100 | 200 |
  | Advanced | 300 | 300 | 200 |
  | Expert | 600 | 600 | 200 |
  | Premier | 1,200 | 1,200 | 500 |
  | Paragon | 2,400 | 2,400 | 750 |
  | Prime | 4,800 | 4,800 | 1,000 |
  | Prestige | 12,000 | 9,600 | 1,000 |

  - **Basic:** account signup.
  - **Advanced:** at least one API order among your last 100 orders, then call the "Upgrade Account API Usage Level" endpoint (costs 30 write tokens).
  - **Expert and above:** trailing 30-day volume share. Earn/keep thresholds are 0.075%/0.05% for Expert up to 1.00%/0.80% for Prestige.
  - **Batch orders:** batch create costs 10 tokens per order and batch cancel costs 2 tokens per order. Batching does not save tokens.
  - **429 handling:** no `Retry-After` header, so use exponential backoff.
  - Source: [Kalshi Rate Limits](https://docs.kalshi.com/getting_started/rate_limits.md)
- **Order mechanics (V2):**
  - The legacy `/portfolio/orders` write endpoints (create, cancel, amend, decrease and their batch forms) "have been removed and now return `410 Gone`."
  - V2 uses a single-book `bid`/`ask` side and fixed-point dollar prices.
  - Required fields include `ticker`, `price`, `time_in_force` and `self_trade_prevention_type`.
  - Flags include `post_only`, `reduce_only` and `cancel_order_on_pause`.
  - `time_in_force` values include `good_till_canceled` (optionally with `expiration_time`) and `immediate_or_cancel`. IOC cannot be combined with `expiration_time`.
  - A `201` means accepted, not resting, so check `remaining_count`.
  - Source: [Kalshi Create Order V2](https://docs.kalshi.com/api-reference/orders/create-order-v2.md)
- **Batch, amend, order groups and subaccounts:**
  - Maximum batch size scales with your tier's write budget, and batches are not atomic.
  - Amend can change price, max fillable count and/or expiration.
  - **Order Groups** auto-cancel every order in the group when a rolling 15-second contract limit is hit. You can trigger or reset a group manually, which works as a built-in kill switch.
  - **Subaccounts** isolate balances and positions.
  - Source: [Kalshi docs index](https://docs.kalshi.com/llms.txt)
- **Other API features:**
  - Hosted **MCP server** at `https://api.elections.kalshi.com/mcp` over Streamable HTTP. It finds markets and perps, reads prices, rules and orderbooks, and with OAuth reads the portfolio and manages price alerts. The doc does not describe order placement through MCP. — [Kalshi MCP](https://docs.kalshi.com/getting_started/mcp.md)
  - RFQ, on-request weather and concert markets, a CF Benchmarks REST passthrough, and "Live Data" endpoints for sports game status. — [Kalshi docs index](https://docs.kalshi.com/llms.txt)
  - **Perps** with separate rate budgets. — [Kalshi Rate Limits](https://docs.kalshi.com/getting_started/rate_limits.md)
- **FIX:** the rate-limit page mentions FIX cancels for perps, but the getting-started pages do not link to FIX docs. — [Kalshi Rate Limits](https://docs.kalshi.com/getting_started/rate_limits.md)
- **Funding (third-party summary):** ACH deposits and all withdrawals are free; debit-card deposits cost up to 2%; there is no settlement or membership fee. — [QuantVPS](https://www.quantvps.com/blog/kalshi-fees-explained); [Predictefy](https://blog.predictefy.com/kalshi-fees)

**Polymarket US (CFTC-regulated; QCX LLC / QC Clearing)**
- **Access:**
  - Download the Polymarket US app, complete identity verification (KYC), then create a Key ID and Secret Key at `polymarket.us/developer`. The secret is shown only once.
  - An invite code may be needed; the docs say to email support@polymarket.us.
  - Source: [Polymarket US Quickstart](https://docs.polymarket.us/getting-started/quickstart.md)
- **Launch timeline (third-party):** the exchange launched invite-only on 2025-12-03, and public API access followed on 2026-02-16. — [QuantVPS](https://www.quantvps.com/blog/polymarket-us-api-available); [Predictefy](https://blog.predictefy.com/polymarket-us-api)
- **Auth:**
  - Ed25519 signatures with headers `X-PM-Access-Key`, `X-PM-Timestamp` (milliseconds) and `X-PM-Signature`.
  - The signed message is `timestamp + method + path`, and the timestamp must be within 30 seconds of server time.
  - Authenticated host: `https://api.polymarket.us/v1/...`.
  - Public market-data endpoints need no key.
  - Source: [Polymarket US Authentication](https://docs.polymarket.us/api-reference/authentication.md)
  - A third-party guide names the public host as `gateway.polymarket.us`. — [Predictefy](https://blog.predictefy.com/polymarket-us-api)
- **SDKs:** `pip install polymarket-us` (Python 3.10+) and `npm install polymarket-us` (Node 18+). — [Polymarket US Quickstart](https://docs.polymarket.us/getting-started/quickstart.md)
- **Order model:**
  - One instrument per market (YES). Selling YES is equivalent to buying NO, and prices always refer to YES.
  - Order types: limit and market.
  - Time in force: GTC, GTD, IOC and FOK.
  - Positions can be long or short YES.
  - Source: [Polymarket US Orders](https://docs.polymarket.us/concepts/orders.md)
- **Endpoints:** Preview Order, Modify Order, Close Position Order, Cancel All, batch create/cancel/modify (up to 20 orders), combos and RFQ, a Private WebSocket (orders, positions, balances) and a Markets WebSocket (book and trades). — [Polymarket US docs index](https://docs.polymarket.us/llms.txt)
- **Rate limits:**
  - General Retail API limit of **25 requests/s**, enforced per source IP and Cloudflare location, so different keys from the same IP share counters.
  - `POST /v1/combos` and `/v1/rfqs` are limited to 1 request/s.
  - For higher limits for automated systems, email support.
  - A **5-second latency stopgap** rejects unprocessed new orders and cancel/replace requests with "Order Processing Max Delay Exceeded" (formerly "Global Rate Limit Exceeded"). That message means latency, not a rate limit, and pure cancels are never rejected.
  - Source: [Polymarket US Rate Limits](https://docs.polymarket.us/api-reference/rate-limits.md)
  - Third-party sources conflict: one says 20 requests/s and another says 25 requests/s (checked 2026-10-10). The official page says 25. — [Predictefy](https://blog.predictefy.com/polymarket-us-api)
- **Funding:** debit card, ACH (via Aeropay), Apple Pay, PayPal, Venmo, USDC and wire. Withdrawals are "secure and free." Fractional contracts are supported. — [Polymarket US docs index](https://docs.polymarket.us/llms.txt)
- **No demo environment is documented** in the Polymarket US docs index. — [Polymarket US docs index](https://docs.polymarket.us/llms.txt)

**Polymarket international (Polygon, on-chain settlement)**
- **US access:**
  - The geoblock endpoint is `GET https://polymarket.com/api/geoblock`.
  - "United States (US)" and "US Minor Outlying Islands" appear under "Regulatory-Restricted Jurisdictions (Close-Only on Frontend and API)": users can close existing positions but cannot open new ones.
  - Orders from blocked regions are rejected.
  - Source: [Polymarket Geographic Restrictions](https://docs.polymarket.com/api-reference/geoblock.md)
- **APIs:**
  - **Gamma** (`https://gamma-api.polymarket.com`): discovery and metadata.
  - **CLOB** (`https://clob.polymarket.com`): prices, books and orders.
  - **Data API** (`https://data-api.polymarket.com`): positions and activity.
  - **Relayer** (`https://relayer-v2.polymarket.com`): gasless transactions.
  - **WebSockets:** CLOB market and user channels, RTDS (`wss://ws-live-data.polymarket.com`) and a Sports WebSocket.
  - **Auth:** L1 is an EIP-712 wallet signature that creates credentials; L2 is HMAC-SHA256 request signing. Orders are also wallet-signed.
  - Source: [Polymarket API](https://docs.polymarket.com/getting-started/api.md)
- **Collateral:** pUSD, an ERC-20 on Polygon with 6 decimals, backed by USDC with the backing enforced on-chain. You wrap USDC.e into pUSD through the `CollateralOnramp` contract. — [Polymarket pUSD](https://docs.polymarket.com/concepts/pusd.md)
- **Order types:**
  - Limit orders are GTC or GTD.
  - GTD orders expire 1 minute before their stated expiry, and the expiry must be at least 3 minutes in the future.
  - Market orders are supported.
  - Order statuses are `live`, `matched` and `delayed`.
  - V2 markets use `positionId`; legacy CTF markets use `tokenId`.
  - Source: [Polymarket Place Orders](https://docs.polymarket.com/trading/place-orders.md)
- **Other trading features:** session keys ("a separate signer for scoped, time-limited Deposit Wallet trading"), plus matching-engine restarts with a post-restart post-only mode. — [Polymarket docs index](https://docs.polymarket.com/llms.txt)
- **Gas and rate limits:** gasless trading is subsidized through the Relayer. The Builder tiers are Unverified (100 relayer transactions/day), Verified (10,000/day) and Partner (unlimited). A personal Relayer API key gives "unlimited daily Relay transactions." API rate limits are "Standard" for Unverified and Verified builders. — [Polymarket Builder Tiers](https://docs.polymarket.com/programs/builders/tiers.md)

**Interactive Brokers ForecastEx (ForecastTrader)**
- **TWS API contract spec:** `secType="OPT"`, `exchange="FORECASTX"`, `currency="USD"`. YES maps to Call and NO maps to Put. — [IBKR TWS API Event Contracts](https://www.interactivebrokers.com/docs/tws-api/contracts/event-contracts.md)
- **Order rules:**
  - Limit orders only, with TIF DAY, GTC or IOC.
  - No cash-quantity orders; whole contracts only.
  - **No sell orders on ForecastEx.** You reduce exposure by buying the opposite contract, and IB nets the positions automatically.
  - Market scanners do not cover event contracts.
  - KALSHI and CME also appear as exchange values for event contracts, and CME event contracts allow both buying and selling.
  - Source: [IBKR TWS API Event Contracts](https://www.interactivebrokers.com/docs/tws-api/contracts/event-contracts.md); [IBKR event trading docs](https://www.interactivebrokers.com/docs/tws-api/doc/event-trading/introduction.md)
- **Web API:** event-contract discovery through `secdef/search`, e.g. `symbol=FF` for Fed Funds. — [IBKR Web API Event Contracts](https://www.interactivebrokers.com/docs/web-api/v1/endpoints/event-contracts/introduction.md)

**Robinhood**
- No event-contract trading API was found.
  - Robinhood's AI agentic trading beta (via MCP) launched on 2026-05-27 for equities only. Event contracts are "on the roadmap" with no timeline. — [PredictionNews](https://predictionnews.com/story/robinhood-launches-beta-support-for-ai-agentic-trading-and-payments-bb7c05f1)
  - Predictefy says Robinhood's public trading API covers crypto only. — [Predictefy](https://blog.predictefy.com/robinhood-prediction-markets-enable)
- Robinhood routes event-contract flow across its in-house exchange, Rothera, Kalshi and others. Q2 2026 revenue from the segment was reportedly $156M. — [IBTimes](https://www.ibtimes.com/robinhood-going-deeper-prediction-markets-its-event-contract-business-growing-3807245)

**Crypto.com (Crypto.com | Derivatives North America)**
- The Predictions market-data REST API is free for "personal, non-commercial use under the EULA. No key, no registration." Commercial use requires a Market Data License Agreement (MDLA). — [Crypto.com Predictions API](https://data.crypto.com/)
- No documented order-placement API for prediction contracts was found. The Exchange API order endpoints cover spot, margin, perps and futures. — [Crypto.com Exchange API](https://crypto.com/exchange-pro/en-US/api); [Crypto.com Help: Prediction Trading](https://help.crypto.com/en/articles/11373970-prediction-trading)

**Novig (sports event contracts)**
- **Account and keys:** a management key opens subaccounts, and each subaccount gets a trading key. Requests are signed with the "NOVIG-V3" scheme.
- **Interfaces:** REST plus streaming channels for book, tape, lifecycle and private updates, plus parlay RFQ for makers.
- **Public data:** two anonymized CSVs a day (trades and markets).
- Source: [Novig API docs index](https://docs.novig.com/llms.txt)

**Gemini Predictions**
- Gemini added batch orders of up to 20 per request to its Predictions product. — [CryptoBriefing](https://cryptobriefing.com/gemini-predictions-batch-orders-world-cup-features/)

**PredictIt**
- Reported to have no trading API and to prohibit automated trading. It publishes a free, non-commercial market-data feed that refreshes about every 60 seconds.
- Sources: PredictIt support article (the fetch failed in this session because of a redirect loop, so this relies on the search summary) — [PredictIt support](https://predictit.freshdesk.com/support/solutions/articles/12000001878-does-predictit-make-market-data-available-via-an-api-); [CryptoSlate review](https://cryptoslate.com/prediction-markets/predictit-review/)

**Manifold (play money)**
- The API ToS explicitly permits "Building bots, automated trading systems, algorithmic tools."
- Rate limit: 500 requests per minute per IP.
- Commercial AI training on API data requires a license.
- Source: [Manifold API](https://docs.manifold.markets/api)
- Official example bots exist: `manifoldmarkets/market-maker` and `simple-trader`. — [GitHub manifoldmarkets](https://github.com/manifoldmarkets)

**Others (Limitless, Myriad, Opinion, Probable, Smarkets, Metaculus)**
- These are supported by the pmxt unified library. Hosted trading "writes today" cover Polymarket, Opinion and Limitless. — [pmxt README](https://github.com/pmxt-dev/pmxt)

### Inferences
- **Best US starting point: Kalshi.**
  - It has a demo environment with identical API shapes.
  - Most series charge makers nothing.
  - The Basic tier allows about 10 order writes/s, which is ample for an LLM agent that trades a few times a day.
  - It has the deepest liquidity (about 81% of October 2026 volume; see Q3).
- **Second US venue: Polymarket US.** It is the natural second venue for cross-venue price comparison or arbitrage. Note that its 25 requests/s limit is per IP, and its taker fee for a new or small account after its first 7 days (Θ=0.095) is about 36% higher than Kalshi's 0.07.
- **Non-US developers:** Polymarket international's on-chain, wallet-signed flow is more complex (pUSD, EIP-712, relayer). It is only relevant if the developer is not a US person or is building read-only analytics.
- **IBKR ForecastEx:** usable for agents already on IBKR. The buy-opposite-only rule changes the exit logic, and the lack of scanner support makes market discovery awkward.
- **Paper trading:** Manifold is the only venue whose ToS explicitly invites bots. It is useful for end-to-end testing of the forecasting and execution loop with no money at risk, though play-money prices are a weaker benchmark.

### Gaps
- **Kalshi FIX:** access requirements (tier, onboarding) were not found in the getting-started pages.
- **Kalshi KYC:** detailed KYC and eligibility steps were not retrieved (out of scope; another researcher covers regulation).
- **Polymarket international:** exact CLOB rate-limit numbers were not retrieved; the docs only say "Standard."
- **Market orders:** Polymarket international's market-order types (FOK/FAK) were not confirmed in the fetched text. Whether Kalshi V2 still accepts `fill_or_kill` was not confirmed.
- **Crypto.com:** a third-party summary gave its prediction-data API limit as 100 requests/min and 50k/day per IP, but this was not confirmed on the official page.
- **Limitless and Myriad:** US eligibility was not researched.
- **PredictIt:** its official API page could not be fetched.

---

## Q2. Fees: exact formulas, rounding and worked examples of fee drag

### Takeaway
Every major venue now uses the same "parabolic" fee shape: **fee = θ × C × P × (1 − P)**. It peaks at P = 0.50 and shrinks toward the tails, but it is largest as a percentage of capital at low prices.

| Venue | Taker θ | Maker terms |
|---|---|---|
| Kalshi | 0.07 | Usually free; 0.0175 on about 1% of series |
| Polymarket international | 0.04–0.07 by category; geopolitics free | Zero fees; 15–25% rebates |
| Polymarket US (from 2026-11-14) | 0.095 → 0.0695, tiered by 30-day taker volume | Rebates only above $10M maker volume |
| Novig | 0.06, live in-game only | Not covered here |

For a hold-to-settlement trade, the fee per contract equals the minimum edge you need in probability points. At 50¢, that is 1.75 points on Kalshi taker and 2.38 points on Polymarket US Tier 1.

### Cited Findings

**Kalshi**
- **Taker formula:** 0.07 × contracts × price × (1 − price), rounded up to the next cent, on buys and sells. This is under the fee schedule effective July 7, 2026. — [QuantVPS](https://www.quantvps.com/blog/kalshi-fees-explained); [Predictefy](https://blog.predictefy.com/kalshi-fees); [PolyKal](https://polykal.net/kalshi-fees-explained/)
- **Maker fees:**
  - Where a series charges makers, the coefficient is 0.0175, a quarter of the taker rate, and it applies only when the resting order fills.
  - A third-party tally on 2026-11-11 found 15,883 of 16,078 series with taker-only fees. Counts of maker-fee series vary across sources (about 100, 157 or 160).
  - Sources: [QuantVPS](https://www.quantvps.com/blog/kalshi-fees-explained); [Realize.tax](https://realize.tax/kalshi/fees)
- **Fee fields in the API:**
  - Series carry `fee_type` with the values `quadratic`, `quadratic_with_maker_fees`, `quadratic_with_combo_maker_fees` (a 0.5 maker multiplier instead of 0.25) and `flat` (the Specific Trading Fees Table). They also carry a `fee_multiplier`.
  - Events can override series fees.
  - The endpoints "Get Series Fee Changes" and "Get Event Fee Changes" expose scheduled changes.
  - Source: [Kalshi Get Series](https://docs.kalshi.com/api-reference/market/get-series.md); [Kalshi docs index](https://docs.kalshi.com/llms.txt)
- **Fee rounding (API docs):**
  - Fees are computed at $0.000001 granularity (`trade_fee = ceil_6dp(model_fee)`).
  - A rounding fee brings balances back to the account's precision: $0.0001 for direct members and $0.01 for non-direct (FCM-cleared) members.
  - A per-order fee accumulator rebates rounding overpayment, so the total converges to what a single equivalent fill would cost.
  - Source: [Kalshi Fee Rounding](https://docs.kalshi.com/getting_started/fee_rounding.md)
  - *Possible conflict:* third-party summaries of the fee schedule say "rounded up to the next cent." The API docs describe sub-cent precision for direct members. Builders should reconcile actual fills against `GET /portfolio/fills`.

**Polymarket international**
- **Formula:** "fee = C × feeRate × p × (1 - p)", in USDC, applied at match time. Makers pay no fees.
- **Taker feeRate by category:**

  | Category | Taker feeRate |
  |---|---|
  | Crypto | 0.07 |
  | Sports | 0.05 |
  | Economics, Culture, Weather, Other | 0.05 |
  | Finance, Politics, Mentions, Tech | 0.04 |
  | Combos | 0.05 |
  | Geopolitics | 0 ("does not charge fees") |

- **Maker rebates:** 20% of taker fees (crypto), 15% (sports), 25% (others).
- **Rounding:** fees are rounded to 5 decimals; the minimum fee is 0.00001 USDC.
- **Deposits and withdrawals:** Polymarket charges nothing for deposits or withdrawals.
- Source: [Polymarket Fees](https://docs.polymarket.com/trading/fees.md)
- **Maker rebate payouts:** paid daily in pUSD with a $1 minimum payout. Fee-free markets (including "fee holidays") earn no rebate. — [Polymarket Maker Rebates](https://docs.polymarket.com/programs/maker-rebates.md)
- **Taker Rebate Program (live 2026-05-28):**
  - Weighted volume: wV = trade size × (1 − entry price) × category weight. Weights are sports 1.0, politics/finance 1.3, economics/other 1.7, crypto 2.3 and geopolitics 0.
  - Tiers run from Bronze (3% rebate at $2k wV) to Obsidian (50% at $10M+ wV).
  - Source: [Polymarket Taker Rebates](https://docs.polymarket.com/programs/taker-rebates.md)

**Polymarket US (effective 2026-11-14)**
- **Formula:** "Fee = Θ × C × p × (1 - p)".
- **Taker Θ by trailing-30-day taker volume:**

  | Tier | Trailing-30-day taker volume | Θ |
  |---|---|---|
  | 1 | < $10k | 0.095 |
  | 2 | $10k – <$50k | 0.085 |
  | 3 | $50k – <$250k | 0.075 |
  | 4 | ≥ $250k | 0.0695 |

- **New-account onboarding:** days 1–7 use Θ = 0.0695. Days 8–30 use the higher of first-7-day volume × 30/7 and trailing volume.
- **Maker rebates:** Θ of −0.0035, −0.0070 and −0.0104, but only for maker volume of at least $10M, $50M and $200M respectively. Below $10M there is no maker rebate.
- **Taker rebates:** 3% at $250k up to 30% at $50M or more.
- **Volume definition:** volume = C × price of the side received, not face value.
- **Coefficient lock:** the fee coefficient is set when the order is inserted.
- Source: [Polymarket US Fee Schedule](https://docs.polymarket.us/fees.md)
- **Prior schedule (third-party):** a taker Θ of 0.06 and a maker rebate Θ of 0.0125 "since July 1, 2026." — [Predictefy / search summary](https://blog.predictefy.com/polymarket-us-api)

**Novig**
- Fee = c × P(1 − P) × N. Since 2026-10-15, c = 0.06 on every straight contract.
- The fee applies only while the underlying event is live.
- Fees are charged exactly to 5 decimals, with no cent rounding and no minimum.
- The API's `qty` field is in 1/100 contract units.
- Source: [Novig Trading Fees](https://docs.novig.com/fees.md)

**Worked examples** (computed from the formulas above)

Taker fee per 100 contracts, in dollars. Dividing by 100 gives cents per contract, which equals the probability points of edge consumed.

| Price | Kalshi taker 0.07 | Kalshi maker 0.0175 | PM-intl crypto 0.07 | PM-intl sports 0.05 | PM-intl politics 0.04 | PM-US Tier 1 0.095 | PM-US Tier 4 0.0695 | Novig live 0.06 |
|---|---|---|---|---|---|---|---|---|
| 0.05 / 0.95 | 0.34 | 0.09 | 0.33 | 0.24 | 0.19 | 0.45 | 0.33 | 0.29 |
| 0.10 / 0.90 | 0.63 | 0.16 | 0.63 | 0.45 | 0.36 | 0.86 / 0.85 | 0.63 | 0.54 |
| 0.20 | 1.12 | 0.28 | 1.12 | 0.80 | 0.64 | 1.52 | 1.11 | 0.96 |
| 0.30 / 0.70 | 1.47 | 0.37 | 1.47 | 1.05 | 0.84 | 1.99 / 2.00 | 1.46 | 1.26 |
| 0.50 | 1.75 | 0.44 | 1.75 | 1.25 | 1.00 | 2.38 | 1.74 | 1.50 |

These match the official samples: Polymarket shows 100 shares at $0.50 costing $1.75 (crypto), $1.25 (sports) and $1.00 (politics) — [Polymarket Fees](https://docs.polymarket.com/trading/fees.md). Polymarket US Tier 4 shows a $1.74 maximum per 100-lot — [Polymarket US Fees](https://docs.polymarket.us/fees.md).

Kalshi taker fee as a percentage of the cost of buying YES, with per-order ceiling to the cent:

| Contracts | P = 0.05 | P = 0.10 | P = 0.30 | P = 0.50 | P = 0.70 | P = 0.90 | P = 0.95 |
|---|---|---|---|---|---|---|---|
| 1 | $0.01 (20%) | $0.01 (10%) | $0.02 (6.7%) | $0.02 (4.0%) | $0.02 (2.9%) | $0.01 (1.1%) | $0.01 (1.1%) |
| 10 | $0.04 (8%) | $0.07 (7%) | $0.15 (5%) | $0.18 (3.6%) | $0.15 (2.1%) | $0.07 (0.8%) | $0.04 (0.4%) |
| 100 | $0.34 (6.8%) | $0.63 (6.3%) | $1.47 (4.9%) | $1.75 (3.5%) | $1.47 (2.1%) | $0.63 (0.7%) | $0.34 (0.4%) |

Round trip (enter and exit as taker at the same price on Kalshi) costs 3.5 points at 50¢, 2.94 points at 30¢ or 70¢, and 1.26 points at 10¢ or 90¢.

### Inferences
- **Fee drag scales with how often you trade.**
  - A hold-to-settlement taker strategy needs more than about 1.75 points of edge at mid-prices on Kalshi.
  - An enter-and-exit strategy needs more than about 3.5 points.
  - Penny-sized orders on Kalshi pay disproportionately because of cent rounding: 1 contract at 5¢ pays 20% of cost, if the ceil-to-cent rule applies. Batch your size.
- **Polymarket US is now the most expensive taker venue for a small account** (Θ = 0.095 after the 7-day onboarding window). The change came only two days before this research date, so expect third-party guides that still quote 0.06 to be stale.
- **Resting limit orders are structurally favored.** They pay zero fees on most Kalshi series, all Polymarket international markets and Polymarket US. An agent that posts limit orders at its fair value and waits gets filled without fees, but faces adverse-selection risk.
- **Prefer cheaper categories where an edge exists.** Polymarket international politics and finance (θ = 0.04) and geopolitics (θ = 0) are cheaper than crypto (θ = 0.07), but they are not available to US residents.

### Gaps
- The Kalshi fee schedule PDF (`kalshi.com/docs/kalshi-fee-schedule.pdf`) returned HTTP 429. Exact text for "flat" or reduced-fee series (for example, any index-market multiplier) and the authoritative cent-rounding rule were not verified first-hand.
- Polymarket international gas costs for non-relayer (self-custody) transactions were not quantified.
- The IBKR ForecastEx commission schedule was not researched.

---

## Q3. Liquidity: order book depth, spreads by category, total volume by platform (2026)

### Takeaway
Volume is heavily concentrated. In October 2026, Kalshi did about $98B of the roughly $121B total (counted at contract face value), and sports dominates Kalshi flow. Sports books are the deepest and tightest. Non-sports and niche markets open with wider spreads. Reliable cross-venue spread and depth statistics by category do not exist publicly; builders should measure them from live books.

### Cited Findings
- **October 2026 totals (DeFi Rate):** about $120.7B across 8 exchanges, up 64.1% from September's $73.58B. Kalshi had $98.15B (81.3%) and Polymarket US had $14.77B. — [DeFi Rate](https://defirate.com/news/prediction-market-volume-reaches-120-7-billion-october/)
- **October 2026 totals (Tokenpost):** $123.3B total, with Kalshi at $98.2B and Polymarket at $20.2B. Tokenpost notes that Kalshi's tally counts each contract at its $1 face value. — [Tokenpost](https://www.tokenpost.com/news/investing/46214)
- **Dollar basis:** Kalshi traded about $16.9B in October 2026 and Polymarket US about $3.43B. — [Totalis](https://www.totalis.trade/blogs/prediction-markets/prediction-market-volume)
- **Robinhood:** customers traded a record 13.6B event contracts in Q2 2026. — [IBTimes](https://www.ibtimes.com/robinhood-going-deeper-prediction-markets-its-event-contract-business-growing-3807245)
- **Category mix:**
  - A Keyrock/Dune report put sports at about 85% of Kalshi notional. Polymarket's mix was sports 39%, politics 34% and crypto 18%.
  - A Becker analysis of Kalshi data put sports at about 72% of notional and politics at 13%.
  - The periods covered were not confirmed.
  - Sources: [DeFi Rate report](https://defirate.com/news/new-report-prediction-markets-growth-driven-by-non-sports/); [Pew Research](https://www.pewresearch.org/?p=486433)
- **Polymarket launch-window microstructure (IMDEA, Oct 2025–Mar 2026):** "sports markets open near the tick floor with deep, balanced books, while non-sports categories open" with higher costs. — [IMDEA paper](https://dspace.networks.imdea.org/bitstream/handle/20.500.12761/2065/Polymarket_Initial_Liquidity-3.pdf?sequence=1)
- **Polymarket tick-level study (Dubach, arXiv 2604.24366):** 30B order-book events over 52 days. Effective spreads differ by category. — [arXiv 2604.24366](https://arxiv.org/abs/2604.24366)
- **Kalshi adverse-selection study (NBER, 41.6M trades):** single-name contracts show more informed price impact, yet effective spreads are only modestly wider, and makers earn about twice as much per contract. — [NBER paper](https://conference.nber.org/conf_papers/f243677.pdf)
- **Depth snapshot (vendor, 2026-07-28):** a 50,000-contract Fed-decision order on Polymarket US would have walked the book 3.62¢, even though the top-of-book ask was only 1¢ above Kalshi's. — [River Markets](https://www.rivermarkets.com/insights/kalshi-vs-polymarket-us.html)
- **Low-confidence spread figures (methods unclear):** about 2.5% for sports versus 4.8% for novelty markets; 2.4–4.0% depending on liquidity. These numbers do not reconcile. — [NexusFi](https://nexusfi.com/a/prediction-markets/liquidity-prediction-markets); [OddsReference](https://oddsreference.pages.dev/predictions/learn/market-liquidity)

### Inferences
- An LLM-research agent's natural niche (politics, economics, culture, long-dated events) sits in the less liquid, wider-spread part of the market. There, limit orders and patience matter more than speed, and position sizes for a small bankroll ($10–$500) will rarely be depth-constrained.
- Sports has the deepest books but the most professional, fastest competition. An LLM agent's edge there is doubtful.

### Gaps
- No authoritative per-category spread or depth dataset was found for either venue in 2026.
- Polymarket international's October 2026 volume is not separated from Polymarket US in the cited trackers.

---

## Q4. Historical and real-time data for backtesting, and news/search feeds

### Takeaway
- **Trades and candlesticks are freely available:** Kalshi historical endpoints, Polymarket APIs and on-chain logs, Dune, and the free 36 GiB Becker dataset.
- **Historical L2 order books are not offered by either exchange.** Order-book history exists only from vendors that recorded it live, mostly starting late 2025 or 2026.
- **For research and retrieval,** Exa and Tavily cost about $0.004–$0.016 per search. AskNews (used in the Metaculus template bot) has no public per-call price.

### Cited Findings

**Kalshi official data**
- **Live/historical split:** data is partitioned by cutoff timestamps from `GET /historical/cutoff`.
- **Historical endpoints:** `GET /historical/markets`, `/historical/markets/{ticker}/candlesticks`, `/historical/trades`, `/historical/fills`, `/historical/orders` and `/historical/positions`.
- **Not partitioned:** events and series stay on their original endpoints.
- Source: [Kalshi Historical Data](https://docs.kalshi.com/getting_started/historical_data.md)
- **Candlesticks:** 1-minute, 60-minute and 1,440-minute intervals.
- **Public trades:** `GET /markets/trades` returns all trades, including block trades.
- **Order books:** only the current book (`GET /markets/{ticker}/orderbook`, plus a multi-market variant), returning YES bids and NO bids only.
- Source: [Kalshi docs index](https://docs.kalshi.com/llms.txt)
- **Specs:** OpenAPI (`docs.kalshi.com/openapi.yaml`) and AsyncAPI (`asyncapi.yaml`) are the source of truth. — [Kalshi SDKs](https://docs.kalshi.com/sdks/overview.md)

**Polymarket official data**
- Gamma (metadata), CLOB (prices and books), the Data API (positions and activity, now v2) and the WebSocket market channel. — [Polymarket API](https://docs.polymarket.com/getting-started/api.md); [Polymarket docs index](https://docs.polymarket.com/llms.txt)
- Polymarket's price-history endpoint returns prices without sizes (third-party). — [search summary citing Bagtester](https://bagtester.com/polymarket)
- Public subgraph: `Polymarket/polymarket-subgraph` (223★, last push 2026-02-13). — [GitHub](https://github.com/Polymarket/polymarket-subgraph)

**Dune**
- Polymarket data since November 2022 (Polygon) and Kalshi since June 2021, with hourly candlesticks.
- Access through SQL, an API, MCP, and Datashare to Snowflake, BigQuery, Databricks or S3.
- Unified Kalshi + Polymarket data announced in May 2026.
- Sources: [Dune blog](https://dune.com/blog/kalshi-and-polymarket-data-unified-on-dune-a-macro-and-equity-signal-source); [CrowdFundInsider](https://www.crowdfundinsider.com/2026/05/280950-dune-analytics-unifies-prediction-markets-data-from-polymarket-and-kalshi/)

**Free bulk dataset**
- `Jon-Becker/prediction-market-analysis`: 3,944★, last push 2026-10-29.
- Billed as "the largest publicly available dataset of Polymarket and Kalshi market and trade data." It is a 36 GiB compressed Parquet download, with indexers to continue collection.
- Cited in 2026 papers, including Kalshi Research's "Who Calibrates Markets?"
- Source: [GitHub README](https://github.com/Jon-Becker/prediction-market-analysis)

**Order-book vendors (all self-reported)**

| Vendor | Coverage | Notes |
|---|---|---|
| PredictionData.dev | Polymarket WebSocket capture since November 2025 | Polymarket plan $1,250/month |
| Telonex | Polymarket order books since 2025-10-11; on-chain fills since inception | Free dataset downloads |
| Oddpool | Kalshi snapshots since 2026-03-19; Polymarket since 2026-03-20 | Parquet |
| Dome | Kalshi order book since 2025-10-29 | |
| Predexon | Kalshi since 2026-01-07 | |
| EntityML | Partial, non-continuous coverage | |
| MarketLens | Polymarket replay with latency and queue modeling | |
| Bitquery | On-chain Polymarket trades only | No depth |

- Oddpool: "Neither exchange provides historical backfill."
- Sources: [PredictionData.dev FAQ](https://predictiondata-dev.pages.dev/faq); [Telonex datasets](https://telonex.io/datasets); [Oddpool docs](https://docs.oddpool.com/kalshi/orderbook); [Dome docs](https://docs.domeapi.io/api-reference/endpoint/get-kalshi-orderbook-history); [Predexon docs](https://docs.predexon.com/api-reference/kalshi/orderbooks); [EntityML](https://docs.entityml.com/); [Bitquery](https://docs.bitquery.io/docs/cloud/polymarket/)
- **Multi-venue data API:** FinFeedAPI/CoinAPI covers 9 prediction platforms. — [CoinAPI blog](https://www.coinapi.io/blog/prediction-markets-are-growing-finfeedapi-now-covers-9-major-platforms)
- **Novig:** daily anonymized trade and market CSVs. — [Novig docs](https://docs.novig.com/llms.txt)

**News and search APIs for agents**
- **Exa:**
  - Search: $4 per 1,000 requests (lite), $7 (auto), $12 (deep / deep-lite) and $15 (legacy deep-reasoning).
  - Contents: $1 per 1,000 pages.
  - Agent product: $0.012–$1.00 per request.
  - Prepaid credits, no subscription.
  - Source: [Exa pricing](https://exa.ai/docs/reference/pricing); [Exa pricing page](https://exa.ai/pricing)
- **Tavily:** basic search costs 1 credit and advanced costs 2 credits. Pay-as-you-go is $0.008 per credit, with 1,000 free credits/month. — [Costbench/Tavily](https://www.costbench.com/software/web-scraping/tavily/); [ColdIQ](https://coldiq.com/blog/tavily-pricing)
- **AskNews:** no official per-request price was found; aggregators list "contact us" or monthly tiers. — [Creati.ai](https://creati.ai/ai-tools/asknews)
- **Metaculus usage:** the Metaculus AskNews reference notebook uses 2 API calls per question. — [Metaculus AIB Q3 project](https://www.metaculus.com/project/aibq3/)
- **Venue-native feeds:** Kalshi "Live Data" (sports game status), the CF Benchmarks passthrough, and Polymarket's Sports WebSocket and RTDS reference prices. — [Kalshi docs index](https://docs.kalshi.com/llms.txt); [Polymarket API](https://docs.polymarket.com/getting-started/api.md)

### Inferences
- **Starting stack for LLM-forecast backtests:**
  1. Resolved markets plus trade-level price paths (Becker dataset or Kalshi historical endpoints).
  2. Point-in-time news.
  3. Simulated limit-order fills against trades rather than books.

  Execution-realistic, depth-aware backtests need a paid vendor and only cover about 12 months.
- **Look-ahead leakage is the main backtest hazard for LLM forecasters.** Model training cutoffs and search engines return post-event information. A clean evaluation needs forward (live or paper) testing, which supports the "demo/paper first" pattern.

### Gaps
- Perplexity Sonar API pricing was not retrieved.
- AskNews official pricing could not be confirmed.
- No reputable Kaggle dataset was verified in this session.
- Polymarket Data API v2 rate limits were not retrieved.

---

## Q5. Open-source tooling: what to start from (maturity as of 2026-11-16)

### Takeaway
Start from the **official SDKs**:
- **Kalshi:** `kalshi_python_sync`, `kalshi_python_async` or `kalshi-typescript`, or a client generated from the OpenAPI spec, which Kalshi recommends for production.
- **Polymarket US:** `polymarket-us`.
- **Polymarket international:** the unified `polymarket-client` or `@polymarket/client`.

For cross-venue work, **pmxt** (2.2k★) and **CCXT** (which now lists Kalshi and Polymarket among 9 prediction venues) are the unified layers. For the forecasting half, **Metaculus `forecasting-tools`** is the most actively maintained template. The original `Polymarket/agents` is archived and pins pre-2026 Polymarket APIs, so treat it as a reference design only.

### Cited Findings
Star counts and last-push dates are from the GitHub API on 2026-11-16.

**Official clients**
- **Polymarket legacy clients are archived:** `Polymarket/py-clob-client` (1,227★, archived, last push 2026-05-25) and `Polymarket/clob-client` (514★, archived).
- **Polymarket current clients:**
  - `py-clob-client-v2` (168★, 2026-11-12)
  - `clob-client-v2` (76★, 2026-11-16)
  - `rs-clob-client-v2` (148★)
  - Unified `py-sdk` (154★, 2026-11-16) and `ts-sdk` (48★)
  - `polymarket-us-python` (35★) and `polymarket-us-typescript` (17★), both 2026-10-09
  - `real-time-data-client` (231★)
  - Source: [GitHub Polymarket org](https://github.com/Polymarket)
- **Polymarket docs:** the unified SDKs are `@polymarket/client` (TypeScript) and `polymarket-client` (Python). A unified Rust SDK is "in development." A migration guide exists from the legacy SDKs. — [Polymarket SDKs & APIs](https://docs.polymarket.com/getting-started/sdks-apis.md)
- **Kalshi:** the old `kalshi-python` package is deprecated in favor of `kalshi_python_sync`, `kalshi_python_async` and `kalshi-typescript`. SDKs publish weekly (Tuesday–Wednesday) and "may lag the API." For production, Kalshi recommends "generating your own client from those specs." — [Kalshi SDKs](https://docs.kalshi.com/sdks/overview.md)
- `Kalshi/kalshi-starter-code-python`: 101★, last push 2025-03-07, which makes it stale relative to the V2 order endpoints. — [GitHub](https://github.com/Kalshi/kalshi-starter-code-python)

**Unified libraries**
- **pmxt-dev/pmxt:** 2,215★, last push 2026-09-30, MIT license, "CCXT for prediction markets."
  - Supports Polymarket, Polymarket US, Kalshi, Limitless, Probable, Baozi, Myriad, Opinion, Metaculus, Smarkets and others.
  - Offers a hosted unified API with hosted trading "writes today" for Polymarket, Opinion and Limitless, plus a self-host option using venue-native credentials.
  - Source: [pmxt README](https://github.com/pmxt-dev/pmxt)
- **ccxt/ccxt:** 44,895★, last push 2026-11-16. It "currently supports the following 9 prediction market exchanges," including Kalshi, Polymarket and Binance, and has a Rust `ccxt-prediction` crate. — [CCXT README](https://github.com/ccxt/ccxt)

**Agent and forecasting frameworks**
- **Polymarket/agents:** 3,817★, **archived**, last push 2024-11-05. — [GitHub](https://github.com/Polymarket/agents)
- **Metaculus/forecasting-tools:** 90★, last push 2026-11-14. "A framework for building a AI Forecasting Bot for Metaculus" plus forecasting tools for humans. — [GitHub](https://github.com/Metaculus/forecasting-tools)
- **alsk1992/CloddsBot:** 3,113★, last push 2026-11-13. An autonomous AI trading agent across Polymarket, Kalshi, Binance and others. — [GitHub](https://github.com/alsk1992/CloddsBot)
- **Kalshi-focused LLM bots:**
  - `ryanfrigo/kalshi-ai-trading-bot`: 659★, last push 2026-11-09. A CLI, MCP server and Claude skill.
  - `OctagonAI/kalshi-trading-bot-cli`: 416★, last push 2026-10-01. Runs research and generates independent probabilities.
  - Source: [GitHub search](https://github.com/search?q=kalshi+bot&type=repositories)
- **MCP servers:**
  - `caiovicentino/polymarket-mcp-server`: 751★, 45 tools.
  - `YichengYang-Ethan/oracle3-prediction-market-agent`: 569★, last push 2026-11-16. Looks for fee-adjusted no-arbitrage violations and includes an MCP server.
  - Kalshi's official hosted MCP (read, portfolio and alerts). — [Kalshi MCP](https://docs.kalshi.com/getting_started/mcp.md)

**Market-making and arbitrage bots**
- `warproxxx/poly-maker`: 1,531★, last push 2026-07-09. A Polymarket two-sided market maker.
- `ImMike/polymarket-arbitrage`: 314★, last push 2025-12-09. Polymarket–Kalshi arbitrage.
- `CarlosIbCu/polymarket-kalshi-btc-arbitrage-bot`: 259★. Hourly BTC markets.
- `radioman/polymarket-arbitrage-trading-bot`: 643★. 5-minute BTC/ETH markets.
- `suislanchez/polymarket-kalshi-weather-bot`: 817★. Kalshi KXHIGH weather markets.
- `tarpboi/Prediction-Markets-Trading-Bot-Toolkits`: 533★. Rust; Predict.fun, Polymarket, Kalshi, Limitless.
- `sterlingcrispin/nothing-ever-happens`: 981★. A self-described meme bot that buys "No."
- Source: [GitHub search results, 2026-11-16](https://github.com/search?q=polymarket+bot&type=repositories)

**General engines and lists**
- `nautechsystems/nautilus_trader`: 31,571★, last push 2026-11-16. A production-grade Rust engine. — [GitHub](https://github.com/nautechsystems/nautilus_trader)
- `Lumiwealth/lumibot`: 2,237★. Claims backtest, paper and live trading with AI agents. — [GitHub](https://github.com/Lumiwealth/lumibot)
- Curated list: `aarora4/Awesome-Prediction-Market-Tools` (805★, last push 2026-10-07). — [GitHub](https://github.com/aarora4/Awesome-Prediction-Market-Tools)
- Manifold's official `market-maker` and `simple-trader` bots. — [GitHub manifoldmarkets](https://github.com/manifoldmarkets)

### Inferences
- **Treat any Polymarket repo older than mid-2026 with suspicion.** The pUSD collateral switch, Protocol V2 markets, unified SDKs and the Data API v2 cutover mean code built on `py-clob-client` v1 (including Polymarket/agents and most 2024–2025 bots) likely needs porting. Likewise, any Kalshi bot using legacy `/portfolio/orders` writes is broken, because those return 410.
- **Star counts on bot repos are a weak quality signal.** Many are marketing for paid products or VPS services. Use them for architecture ideas, not as production code.
- **Suggested stack for a US builder:**
  1. A thin, self-written Kalshi client generated from the OpenAPI spec.
  2. `polymarket-us` for Polymarket US.
  3. pmxt or CCXT for normalized market discovery.
  4. Metaculus `forecasting-tools` patterns for the forecasting pipeline.

### Gaps
- Whether NautilusTrader currently ships maintained Polymarket or Kalshi adapters was not verified in this session.
- CCXT's prediction-market support depth (trading versus data only) was not verified.
- Code quality and backtest validity of the community bots were not audited.

---

## Q6. Architecture patterns for an LLM agent trading system

### Takeaway
The recommended pipeline is:

> ingest (WebSocket, not polling) → filter markets (liquidity, time to resolution, fee category) → retrieve news and context → ensemble probability estimate → fee-adjusted edge vs. executable price → fractional-Kelly sizing with hard caps → limit-order execution (post-only where possible) → exchange-native kill switches → log every forecast and score it against the market

The venue APIs now provide several safety primitives an agent should use: Kalshi demo, order groups, subaccounts, `reduce_only`, `cancel_order_on_pause` and self-trade prevention; Polymarket US preview-order and close-position endpoints; and Polymarket session keys.

### Cited Findings

**Ingestion**
- Use WebSockets instead of polling for orders, positions, balances, best bid/offer and books, and cache reference data with a TTL. — [Polymarket US Rate Limits](https://docs.polymarket.us/api-reference/rate-limits.md)
- Kalshi notes a short delay before exchange events appear in REST. "Combine API responses to PUT/POST/DELETE requests with WebSocket data." Order reads can briefly return 404 or stale state after a write. — [Kalshi docs index](https://docs.kalshi.com/llms.txt)

**Testing environments**
- Kalshi demo has separate credentials and mock funds, but its prices are not representative. — [Kalshi Demo Env](https://docs.kalshi.com/getting_started/demo_env.md)
- Manifold explicitly permits bots and automated trading. — [Manifold API](https://docs.manifold.markets/api)

**Pre-trade checks**
- Polymarket US has a "Preview Order" endpoint that validates parameters and shows expected fills. — [Polymarket US docs index](https://docs.polymarket.us/llms.txt)

**Kill switches and risk controls**
- **Kalshi Order Groups:** when a rolling 15-second contract limit is hit, all orders in the group are cancelled and no new ones are allowed until reset. A group can also be triggered manually. — [Kalshi docs index](https://docs.kalshi.com/llms.txt)
- **Polymarket US:** "Cancel All Open Orders" and a "Close Position Order" endpoint. — [Polymarket US docs index](https://docs.polymarket.us/llms.txt)
- **Kalshi order flags:** `reduce_only`, `post_only`, `cancel_order_on_pause` and `self_trade_prevention_type`. — [Kalshi Create Order V2](https://docs.kalshi.com/api-reference/orders/create-order-v2.md)
- **Kalshi subaccounts:** isolate balances and positions per strategy. — [Kalshi Subaccounts](https://docs.kalshi.com/getting_started/subaccounts.md)
- **Polymarket session keys:** authorize "a separate signer for scoped, time-limited" trading, which limits what an agent can do with its credentials. — [Polymarket docs index](https://docs.polymarket.com/llms.txt)

**Execution edge cases**
- **Polymarket US latency stopgap:** new orders not processed within 5 seconds are rejected. Treat this as transient and resubmit; cancels are unaffected. — [Polymarket US Rate Limits](https://docs.polymarket.us/api-reference/rate-limits.md)
- **Polymarket international maintenance:** matching-engine restarts are followed by a post-only period. GTD orders have a 1-minute security threshold and a 3-minute minimum expiry. — [Polymarket docs index](https://docs.polymarket.com/llms.txt); [Polymarket Place Orders](https://docs.polymarket.com/trading/place-orders.md)

**Forecasting quality (Metaculus evidence)**
- In the Fall 2025 Metaculus bot tournament, the top five scaffolded bots beat their non-scaffolded baselines by 5–11 peer-score points per question. — [LessWrong: AI forecasting in 2026](https://www.lesswrong.com/posts/a82q6yd8zKpYk56cF/ai-forecasting-in-2026-what-11-analyses-say)
- A Metaculus write-up titled "Human pros crush bots" (Q1 benchmarking results) indicates that bots still trailed professional forecasters. — [EA Forum: Q1 AI benchmarking results](https://forum-bots.effectivealtruism.org/posts/mwcWxwdsEMexm98GF/q1-ai-benchmarking-results-human-pros-crush-bots)

### Inferences
These are standard practice rather than claims from a single cited source.

- **Edge and sizing:**
  - Compute edge as q − p_exec − fee per contract, using the Q2 table.
  - For buying YES at price p with model probability q, full Kelly is f* = (q − p)/(1 − p).
  - Use 0.1–0.25× Kelly, because LLM probabilities are noisy and overconfident.
  - Cap per-market exposure (e.g. 2–5% of bankroll) and per-event correlated exposure.
- **Execution:**
  - Default to resting limit orders at or inside fair value. They pay zero fees on most Kalshi series and on Polymarket.
  - Reserve IOC or taker orders for cases where edge minus taker fee clearly exceeds a threshold.
- **Evaluation:**
  - Log the market price at forecast time and the model probability.
  - Compute the Brier score of model versus market on resolved markets before committing capital.
  - Attribute P&L to edge, fees, spread and slippage separately.
- **Rollout:**
  1. Paper or shadow mode (forecast and log only).
  2. Kalshi demo for execution plumbing.
  3. Small live stakes (tens of dollars).
  4. Scale only after a statistically meaningful number of resolved forecasts beat the market after fees.
- **Kill switches:** wire exchange-native kill switches (Kalshi order groups, cancel-all) to anomaly triggers. Examples: daily loss limit, repeated rejects, WebSocket disconnects, or model output outside expected bounds.

### Gaps
- No primary source was found with practitioner consensus figures, such as a recommended Kelly fraction or a minimum number of forecasts before going live.
- Builder threads on r/algotrading, r/Kalshi and r/Polymarket were not directly reviewed in this session.

---

## Q7. LLM inference cost per forecast vs. position sizes for a small bankroll

### Takeaway
A single well-researched forecast costs roughly **$0.003–$0.02** with a small model and minimal search. A mid-tier model with about 5 searches costs about **$0.15–$0.20**. An Opus-class deep run or a 5-model ensemble costs about **$0.50–$0.70**.

On a small bankroll this is material, because cost scales with **markets screened**, not trades placed. Example: a $40 quarter-Kelly position with a 10-point edge has about $10 of expected gross profit and about $1.77 of Kalshi taker fee. If the agent screens 20 markets per trade at about $0.17 each, research costs about $3.40 per trade, comparable to or larger than the fee.

### Cited Findings

**Anthropic API list prices** (USD per million tokens, input/output; from the Claude API reference table cached 2026-10-06)

| Model | Input | Output | Cache reads |
|---|---|---|---|
| Claude Opus 5.5 | $4 | $20 | $0.20 |
| Claude Sonnet 5.5 | $2 | $10 | $0.20 |
| Claude Haiku 5.5 | $0.10 | $0.50 | — |

- Haiku 5.5 prices apply to prompts up to 100K tokens; above that they are $0.50 / $2.50.
- The Batch API is 50% off for asynchronous jobs.
- Source: [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing)

**Forecasting-bot cost benchmarks**
- One builder measured the unmodified Metaculus template bot at **$0.109 per question**. After cost cuts (cheaper models, fewer tokens) it fell to **$0.004 per question**: about $55 versus $2 per 500 questions, with an expected performance hit. — [Abstraction Substack: Deploying a Forecasting Bot](https://abstraction.substack.com/p/deploying-a-forecasting-bot)
- Metaculus's Spring 2026 bot-maker survey found self-reported cost per question only weakly correlated with score (r ≈ +0.17, p ≈ 0.30, n = 39). LLM calls per question showed r ≈ +0.20, p ≈ 0.21. — [EA Forum: What AI forecasting strategy works best (Spring 2026)](https://forum.effectivealtruism.org/posts/tJoxFWkRev5wrEBar/what-ai-forecasting-strategy-works-best-spring-2026-survey)
- Lightning Rod (vendor) reports **$3.30 per 1,000 forecasts** in its low-effort mode, about 215 output tokens per forecast, benchmarked on Polymarket questions resolved in Q1 2026. — [Lightning Rod blog](https://blog.lightningrod.ai/p/foresight-v4-better-predictions-cheaper-inference-ccc7)

**Search cost per call:** Exa lite/auto costs $0.004/$0.007; Tavily basic/advanced costs $0.008/$0.016. — [Exa pricing](https://exa.ai/docs/reference/pricing); [Costbench/Tavily](https://www.costbench.com/software/web-scraping/tavily/)

**Worked cost scenarios** (my arithmetic from the list prices above; token counts are assumptions)

| Scenario | Model and tokens | LLM cost | Search | Total per forecast |
|---|---|---|---|---|
| Screen | Haiku 5.5, 20k in / 1.5k out | ≈$0.003 | 2 Tavily basic ≈$0.016 | **≈$0.02** |
| Standard | Sonnet 5.5, 40k in / 4k out (incl. thinking) | $0.08 + $0.04 = $0.12 | 5 Exa auto + 10 pages ≈$0.045 | **≈$0.17** |
| Ensemble | 5 Sonnet 5.5 runs, no caching | ≈$0.60 | ≈$0.05 | **≈$0.65** |
| Deep | Opus 5.5, 100k in / 10k out | $0.40 + $0.20 | ≈$0.10 | **≈$0.70** |

- Prompt caching (cache reads at $0.20/M) cuts the ensemble's repeated-context cost substantially.
- The Batch API halves LLM costs for non-urgent forecasts.

**Position-size comparison** (Kalshi taker fees from the Q2 formula)
- **$1,000 bankroll, market at 0.40, model at 0.50:** full Kelly is 0.10/0.60 = 16.7%; quarter-Kelly is about $42, or 105 contracts. Expected gross profit is 105 × $0.10 = $10.50, and the taker fee is 0.07 × 105 × 0.4 × 0.6 = $1.77. A $0.17 forecast is about 1.6% of expected gross profit, but screening 20 markets per trade is about $3.40 (about 32%).
- **$10 position at 0.50 with a 5-point edge:** 20 contracts, $1.00 expected gross profit, $0.35 taker fee and $0.65 net. A $0.17 forecast eats about 26% of net expected profit; a $0.65 ensemble makes the trade break even.

### Inferences
- **Use a two-stage funnel.**
  1. A cheap model plus market metadata and price filters screens hundreds of markets for about $0.003–$0.02 each.
  2. Expensive research and ensembles run only on markets with plausible edge, adequate liquidity and favorable fee categories.
- **Keep total inference spend to a small fraction of expected edge.** Below a bankroll of a few hundred dollars, LLM and search costs plus fees can consume most of a realistic 3–5 point edge. Small bankrolls are best treated as a paid experiment in forecast validation, not a profit engine.
- **Re-forecasting is often the hidden cost driver.** Re-forecasting a held position daily multiplies cost. Event-triggered re-forecasts (on a news hit or price move) are cheaper.

### Gaps
- No official Metaculus figure for average tokens or dollars per question in 2026 was found.
- OpenAI, Google and xAI API prices were not retrieved, so the cost scenarios cover Anthropic models only.
- Perplexity Sonar and AskNews per-call prices are unconfirmed.
