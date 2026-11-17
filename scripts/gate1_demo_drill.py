"""Gate 1: execution drills against Kalshi's DEMO exchange (fake money).

Needs ~/.config/pmbot/demo/key_id and private_key.pem. Run:  python scripts/gate1_demo_drill.py
Each drill prints PASS or FAIL. Orders are post-only bids far below the market, except the last
drill, which buys one contract to check that a fill is recorded once. All seven passed on 2026-11-16.
The crash is simulated in-process (a ledger row without an acknowledgement), not a killed bot.
"""

import sys
import time
from pathlib import Path

from pmbot.execution.brokers import KalshiBroker, client_order_id
from pmbot.kalshi.client import DEMO, KalshiClient, dollars
from pmbot.ledger.db import Ledger, new_id

creds = Path("~/.config/pmbot/demo").expanduser()
if not (creds / "key_id").exists():
    sys.exit(f"missing {creds}/key_id and private_key.pem; create a key at https://demo.kalshi.co")
client = KalshiClient.from_key_file(DEMO, (creds / "key_id").read_text().strip(), creds / "private_key.pem")
ledger = Ledger("data/gate1_demo.sqlite")
broker = KalshiBroker(ledger, client, "demo", group_contracts_limit=200)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok else "FAIL"), name, detail, flush=True)


def exchange_orders(ticker: str, status: str = "resting") -> list[dict]:
    return [o for o in client.orders(ticker=ticker, status=status)]


print("balance:", client.balance())
client.cancel_all()      # start clean: earlier runs may have left orders resting
from pmbot.kalshi.client import count
# Needs someone actually selling, so the fill drill has something to buy.
market = next(m for m in client.markets(status="open", mve_filter="exclude", max_pages=30)
              if 0.10 <= dollars(m.get("yes_bid_dollars")) < dollars(m.get("yes_ask_dollars")) <= 0.90
              and count(m.get("yes_ask_size_fp")) >= 1)
ticker, far_bid = market["ticker"], 0.02
ledger.insert("markets", {"ticker": ticker, "event_ticker": market["event_ticker"], "series_ticker": "", "status": "active"})
print("using market", ticker, "bid/ask", market["yes_bid_dollars"], market["yes_ask_dollars"])

# 1. A signed post-only order rests on the exchange.
d1 = new_id()
broker.place(d1, ticker, "yes", far_bid, 1, ttl_s=3600)
time.sleep(1)
mine = [o for o in exchange_orders(ticker) if o.get("client_order_id") == client_order_id(d1)]
check("order rests on exchange", len(mine) == 1)

# 2. Replaying the same decision does not create a second order.
broker.place(d1, ticker, "yes", far_bid, 1, ttl_s=3600)
time.sleep(1)
check("replay sends no duplicate", len([o for o in exchange_orders(ticker) if o.get("client_order_id") == client_order_id(d1)]) == 1)

# 3. Crash between submit and acknowledgement: the exchange has the order, the ledger says 'submitting'.
d2 = new_id()
broker._record(client_order_id(d2), d2, ticker, "yes", far_bid, 1, 3600, "submitting")
client.create_order(ticker, "bid", 1, far_bid, client_order_id(d2), expiration_ts=int(time.time()) + 3600,
                    order_group_id=broker.order_group())
time.sleep(1)
broker.sync()
row = ledger.one("SELECT status, exchange_order_id FROM orders WHERE client_order_id=?", [client_order_id(d2)])
check("reconciliation adopts an orphaned order", row["status"] == "resting" and bool(row["exchange_order_id"]), dict(row).__repr__())

# 4. Kill switch: everything cancelled on the exchange, and the order group refuses new orders.
broker.cancel_all("gate1 drill")
time.sleep(1)
check("cancel-all leaves nothing resting", len(exchange_orders(ticker)) == 0)
d3 = new_id()
check("order group blocks new orders after kill", broker.place(d3, ticker, "yes", far_bid, 1, ttl_s=3600) is None)
client.reset_order_group(broker.order_group())
d4 = new_id()
check("orders flow again after group reset", broker.place(d4, ticker, "yes", far_bid, 1, ttl_s=3600) is not None)

# 5. A real fill appears in the ledger exactly once and matches the exchange.
d5 = new_id()
ask = dollars(client.market(ticker).get("yes_ask_dollars"))
broker._record(client_order_id(d5), d5, ticker, "yes", ask, 1, 60, "submitting")
client.create_order(ticker, "bid", 1, ask, client_order_id(d5), post_only=False, time_in_force="immediate_or_cancel")
time.sleep(2)
first, second = broker.sync(), broker.sync()
ours = ledger.one("SELECT COALESCE(SUM(contracts),0) AS n FROM fills WHERE client_order_id=?", [client_order_id(d5)])["n"]
theirs = sum(float(f["count_fp"]) for f in client.fills(ticker=ticker)
             if f.get("order_id") == ledger.one("SELECT exchange_order_id AS e FROM orders WHERE client_order_id=?", [client_order_id(d5)])["e"])
check("fill ingested once and matches exchange", first >= 1 and second == 0 and ours == theirs, f"ledger {ours} exchange {theirs}")

client.cancel_all()
client.reset_order_group(broker.order_group())
failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} drills passed")
sys.exit(1 if failed else 0)
