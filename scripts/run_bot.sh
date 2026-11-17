#!/bin/zsh
# Runs the bot loop. Safe to restart at any time: all state is in the ledger and every
# order is keyed to its decision.
#   ./scripts/run_bot.sh                 paper trading (config/settings.yaml)
#   ./scripts/run_bot.sh demo            demo exchange, fake money, no forecasts (config/demo.yaml)
# `caffeinate -i` keeps the Mac from idle-sleeping while a bot runs; nothing runs while it sleeps.
# It does not stop sleep from closing a laptop lid. Stopping the bot releases it.
cd "$(dirname "$0")/.."
source .venv/bin/activate
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"   # so the `claude` CLI is found
if [[ "$1" == "demo" ]]; then
  export PMBOT_CONFIG=config/demo.yaml
  exec caffeinate -i pmbot cycle --every "${PMBOT_INTERVAL:-300}" --no-forecast >> logs/demo.log 2>&1
fi
exec caffeinate -i pmbot cycle --every "${PMBOT_INTERVAL:-600}" >> logs/bot.log 2>&1
