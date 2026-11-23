#!/bin/zsh
# Build the dashboard and open it in the browser.
#   ./scripts/dashboard.sh            paper account (this machine)
#   ./scripts/dashboard.sh demo       demo account (this machine)
#   ./scripts/dashboard.sh twin       paper copy of the live bot (this machine)
#   ./scripts/dashboard.sh live       live account: built on the server from its ledger, then copied here
# The server's address comes from $PMBOT_SERVER or ~/.config/pmbot/server (one line, like user@host).
cd "$(dirname "$0")/.."
which=${1:-paper}
out="data/dashboard_$which.html"
if [[ "$which" == "live" ]]; then
  host=${PMBOT_SERVER:-$(cat ~/.config/pmbot/server 2>/dev/null)}
  [[ -z "$host" ]] && { echo "set PMBOT_SERVER or write user@host to ~/.config/pmbot/server"; exit 1; }
  ssh "$host" 'cd pmbot && PMBOT_CONFIG=config/live.yaml .venv/bin/pmbot dashboard --out data/dashboard.html' > /dev/null \
    && scp -q "$host:pmbot/data/dashboard.html" "$out" || exit 1
else
  source .venv/bin/activate
  [[ "$which" == "demo" ]] && export PMBOT_CONFIG=config/demo.yaml
  [[ "$which" == "twin" ]] && export PMBOT_CONFIG=config/twin.yaml
  pmbot dashboard --out "$out" > /dev/null || exit 1
fi
echo "$PWD/$out"
[[ -z "$PMBOT_NO_OPEN" ]] && open "$out"
