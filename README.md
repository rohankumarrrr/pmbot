# pmbot

An experiment: can an automated agent make money on [Kalshi](https://kalshi.com) prediction markets after fees? This is the harness that tests it, with go/no-go thresholds fixed before any result came in.

**Status (2026-11-17):** paper trading and Kalshi's demo exchange only. No real money has been traded and nothing here has been shown to be profitable. This is not financial advice.

## What it does

Two strategies share one risk manager and one ledger:

1. **Liquidity rewards (`lp`).** Kalshi pays a daily reward pool to orders resting near the top of the book in several thousand markets. The bot scores live books by the program's rules and rests the quotes with the most reward per dollar at risk, net of what filled orders at that price have historically lost.
2. **Forecast blend (`llm_blend`).** Claude researches an event, a five-model ensemble gives a probability without seeing the price, and the result is blended with a bias-corrected market price. The bot posts a maker order only when the blended edge clears fees and the ensemble's own disagreement.

A price-only baseline is logged for every eligible market, so the forecaster has a free benchmark to beat.

## Modes

| Mode | Orders | Money |
|---|---|---|
| `shadow` | Recorded only; fills inferred from the public trade tape | None |
| `demo` | Sent to Kalshi's demo exchange | Fake |
| `live` | Sent to Kalshi | Real |

`config/settings.yaml` is the paper setup. `config/demo.yaml` overrides it for the demo exchange; select it with `PMBOT_CONFIG=config/demo.yaml`.

## Setup

Needs Python 3.12+ and, for forecasts, the [`claude` CLI](https://claude.com/claude-code) signed in. Market data is public, so paper mode needs no Kalshi account.

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest            # 58 tests, no network
```

## Running it

```sh
pmbot cycle                 # one cycle
pmbot cycle --every 600     # loop, one cycle every 10 minutes
pmbot cycle --no-forecast   # reward quotes only; no model calls
pmbot status                # cash, positions, resting orders, halts
pmbot score                 # forecasts vs the market, and the gate 0 verdict
pmbot lp                    # reward-strategy report
pmbot universe              # events the forecaster would consider
pmbot halt "reason"         # kill switch: cancel everything and stop
pmbot resume
```

- `scripts/run_bot.sh` runs the paper loop and `scripts/run_bot.sh demo` the demo loop. Both log to `logs/` and keep a Mac from idle-sleeping while they run.
- `scripts/check_consistency.py` compares the ledger with the exchange.
- `scripts/checkin.py` prints a JSON health summary of both loops.
- `scripts/gate1_demo_drill.py` runs seven execution drills against the demo exchange.

Each forecast costs about $0.50 of Claude usage and takes about three minutes. `forecast.daily_cost_cap_usd` bounds the spend.

## Credentials for demo and live

Placing orders needs a Kalshi API key, kept outside the project:

```
~/.config/pmbot/demo/key_id            # the key ID, one line
~/.config/pmbot/demo/private_key.pem   # the private key Kalshi shows once
~/.config/pmbot/live/...               # same two files for production
```

Create demo keys at <https://demo.kalshi.co> (Account → API Keys). For live trading, use a key restricted to a dedicated subaccount and set `kalshi.subaccount`, so the bot can never touch more than that subaccount's balance.

## Layout

| Path | What it holds |
|---|---|
| `src/pmbot/kalshi/` | REST client (signing, throttling, retries) and the fee model |
| `src/pmbot/catalog.py`, `universe.py` | Market ingestion and the forecast universe filter |
| `src/pmbot/llm/` | Claude CLI backend and the screen → research → ensemble pipeline |
| `src/pmbot/blend.py` | Calibration, market blend, edge and Kelly sizing |
| `src/pmbot/lp.py`, `lp_runner.py` | Reward scoring per Kalshi's program rules, quote selection and upkeep |
| `src/pmbot/execution/brokers.py` | Simulated broker and the real Kalshi broker |
| `src/pmbot/risk.py`, `portfolio.py`, `consistency.py` | Caps, drawdown halt, positions, ledger-vs-exchange self-check |
| `src/pmbot/score.py` | Brier scores, the information test, and gate checks |
| `config/gates.yaml` | Go/no-go thresholds, fixed before any result was seen |
| `research/` | One-off studies: trade-history sample, reward yields, pipeline trials |

Not in the repository: the ledgers (`data/`), logs, and downloaded Kalshi data (`research/out/`). The scripts in `research/` rebuild the data from Kalshi's public API.

## Docs

- [`docs/DESIGN.md`](docs/DESIGN.md): how the bot works and why.
- [`docs/FINDINGS.md`](docs/FINDINGS.md): what the data showed, including who made money on Kalshi in 2025–2026.
- [`docs/research/REPORT.md`](docs/research/REPORT.md): the background research that started the project, with source notes in `docs/research/notes/`.
