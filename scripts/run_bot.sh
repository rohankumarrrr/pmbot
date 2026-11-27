#!/bin/zsh
# Runs the bot loop. Safe to restart at any time: all state is in the ledger and every
# order is keyed to its decision.
#   ./scripts/run_bot.sh                 paper trading (config/settings.yaml)
#   ./scripts/run_bot.sh demo            demo exchange, fake money, no forecasts (config/demo.yaml)
#   ./scripts/run_bot.sh twin            paper copy of the live bot at live size (config/twin.yaml)
# `caffeinate -i` keeps the Mac from idle-sleeping while a bot runs; nothing runs while it sleeps.
# It does not stop sleep from closing a laptop lid. Stopping the bot releases it.
cd "$(dirname "$0")/.."
source .venv/bin/activate
export TMPDIR=/tmp                                                        # do not inherit an ephemeral caller TMPDIR
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"   # so the `claude` CLI is found
if [[ "$1" == "demo" ]]; then
  export PMBOT_CONFIG=config/demo.yaml
  exec caffeinate -i pmbot cycle --every "${PMBOT_INTERVAL:-300}" --no-forecast >> logs/demo.log 2>&1
fi
if [[ "$1" == "twin" ]]; then
  export PMBOT_CONFIG=config/twin.yaml
  exec caffeinate -i pmbot cycle --every "${PMBOT_INTERVAL:-240}" --no-forecast >> logs/twin.log 2>&1
fi
# LLM forecaster paused 2026-11-27 (Rohan aligned: 0.2610 vs 0.1894 Brier, -$80.46 ex-best event);
# paper still runs LP quoting, settles existing forecasts, and logs price-correction baselines.
exec caffeinate -i pmbot cycle --every "${PMBOT_INTERVAL:-600}" --no-forecast >> logs/bot.log 2>&1
