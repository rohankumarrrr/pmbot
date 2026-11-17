"""Compare the ledger with the exchange. The bot runs the same check every cycle.

Usage: PMBOT_CONFIG=config/demo.yaml python scripts/check_consistency.py
"""
import sys

from pmbot import config
from pmbot.consistency import check
from pmbot.ledger.db import Ledger
from pmbot.runner import trading_client

cfg = config.load()
if cfg.mode == "shadow":
    sys.exit("shadow mode has no exchange side to compare")
ledger = Ledger(cfg.ledger_path)
r = check(ledger, trading_client(cfg), cfg.mode)
print(f"resting orders: exchange {r.exchange_resting}, ledger {r.ledger_resting}")
print(f"  duplicated client IDs on exchange: {len(r.duplicates)} {r.duplicates[:3]}")
print(f"  on exchange but not resting in ledger (orphans): {len(r.orphans)} {r.orphans[:3]}")
print(f"  resting in ledger but not on exchange (stale): {len(r.stale)} {r.stale[:3]}")
print(f"  exchange fills missing from ledger: {len(r.missing_fills)}, size mismatches: {len(r.fill_mismatches)}")
last = ledger.get_state(f"last_consistency:{cfg.mode}")
if last:
    print(f"bot's own last check: {last['summary']} ({int((__import__('time').time() - last['ts']) / 60)} min ago)")
print("CONSISTENT" if r.ok else "INCONSISTENT")
sys.exit(0 if r.ok else 1)
