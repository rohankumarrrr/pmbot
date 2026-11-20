#!/usr/bin/env bash
# One-time setup of the live bot on a fresh Ubuntu 24.04 server (x86 or Arm). A 1 GB server is
# enough: the bot peaks at about 500 MB while it reads the market catalog, and this adds swap
# as a margin.
#
#   curl -fsSL https://raw.githubusercontent.com/rohankumarrrr/pmbot/main/deploy/setup_server.sh | bash
#
# To install code that is not on GitHub yet, copy it first and then run the script there:
#   rsync -az --exclude .git --exclude .venv --exclude data --exclude logs --exclude vendor \
#         --exclude research/out --exclude __pycache__ ./ user@server:pmbot/
#   ssh user@server 'bash pmbot/deploy/setup_server.sh'
#
# It installs the code and a systemd service but does not start trading: the service is enabled
# only once the two credential files exist (see the end of this script).
set -euo pipefail

REPO=https://github.com/rohankumarrrr/pmbot.git
DIR="$HOME/pmbot"
CREDS="$HOME/.config/pmbot/live"

sudo apt-get update -y
sudo apt-get install -y git python3 python3-venv
python3 -c 'import sys; assert sys.version_info >= (3, 12), "Python 3.12 or newer is required"'

if [ ! -f /swapfile ]; then      # a margin for small servers; unused when memory is plentiful
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile > /dev/null && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab > /dev/null
fi

if [ -d "$DIR/.git" ]; then git -C "$DIR" pull --ff-only
elif [ -f "$DIR/pyproject.toml" ]; then echo "using the code already copied to $DIR"
else git clone "$REPO" "$DIR"; fi
cd "$DIR"
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e ".[dev]"
.venv/bin/python -m pytest -q
mkdir -p data logs "$CREDS"
chmod 700 "$HOME/.config/pmbot" "$CREDS"

sudo tee /etc/systemd/system/pmbot-live.service > /dev/null <<UNIT
[Unit]
Description=pmbot live reward quoting (Kalshi)
After=network-online.target
Wants=network-online.target
# Never start without credentials.
ConditionPathExists=$CREDS/key_id
ConditionPathExists=$CREDS/private_key.pem

[Service]
User=$USER
WorkingDirectory=$DIR
Environment=PMBOT_CONFIG=config/live.yaml
ExecStart=$DIR/.venv/bin/pmbot cycle --every 300 --no-forecast
Restart=always
RestartSec=60
StandardOutput=append:$DIR/logs/live.log
StandardError=append:$DIR/logs/live.log

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload

cat <<MSG

Installed in $DIR. Nothing is running yet.

To go live:
  1. Put the Kalshi key ID in      $CREDS/key_id          (chmod 600)
     and the private key in        $CREDS/private_key.pem  (chmod 600)
  2. sudo systemctl enable --now pmbot-live
  3. tail -f $DIR/logs/live.log

Kill switch:  cd $DIR && PMBOT_CONFIG=config/live.yaml .venv/bin/pmbot halt "reason"
Stop the bot: sudo systemctl stop pmbot-live   (resting orders stay on the exchange; use the kill switch to cancel them)
MSG
