#!/bin/zsh
# Change a bot's reward-strategy settings while it runs. The change takes effect on that bot's next
# cycle, with no deploy and no restart, and is written to its risk-event log.
#   ./scripts/control.sh twin settings
#   ./scripts/control.sh twin set lp.max_markets_per_family 2 --why "one family filled four times"
#   ./scripts/control.sh live pause KXAAAGAS --why "answer is published on a schedule"
#   ./scripts/control.sh live unpause KXAAAGAS
#   ./scripts/control.sh paper unset lp.max_markets_per_family
# paper, demo and twin run on this machine; live runs on the server, whose address comes from
# $PMBOT_SERVER or ~/.config/pmbot/server (one line, like user@host).
# Hard limits (lp.max_at_risk_per_quote, lp.capital_fraction, everything under risk and trading) are
# refused here: they are changed in the config file.
cd "$(dirname "$0")/.."
which=$1; shift
case "$1" in set|unset|pause|unpause|settings) ;; *) echo "usage: $0 <paper|demo|twin|live> <settings|set|unset|pause|unpause> ..."; exit 1;; esac
if [[ "$which" == "live" ]]; then
  host=${PMBOT_SERVER:-$(cat ~/.config/pmbot/server 2>/dev/null)}
  [[ -z "$host" ]] && { echo "set PMBOT_SERVER or write user@host to ~/.config/pmbot/server"; exit 1; }
  exec ssh "$host" "cd pmbot && PMBOT_CONFIG=config/live.yaml .venv/bin/pmbot ${(j: :)${(q)@}}"
fi
source .venv/bin/activate
case "$which" in
  paper) ;;
  demo) export PMBOT_CONFIG=config/demo.yaml ;;
  twin) export PMBOT_CONFIG=config/twin.yaml ;;
  *) echo "unknown bot '$which' (paper, demo, twin or live)"; exit 1 ;;
esac
exec pmbot "$@"
