"""The dashboard page is built from the ledger alone."""

import json

from pmbot import config
from pmbot.dashboard import collect, render
from pmbot.execution.brokers import ShadowBroker, client_order_id
from pmbot.ledger.db import Ledger, new_id, now


class NoTape:
    def trades(self, **_):
        return iter(())


def seeded() -> Ledger:
    ledger = Ledger(":memory:")
    ledger.insert("markets", {"ticker": "S-E1-A", "event_ticker": "S-E1", "series_ticker": "S", "status": "active",
                              "title": "Will <b>it</b> happen?", "close_ts": now() + 86400})
    ledger.insert("snapshots", {"ticker": "S-E1-A", "ts": now(), "yes_bid": 0.29, "yes_ask": 0.31})
    broker = ShadowBroker(ledger, NoTape())
    for decision, price in (("d1", 0.40), ("d2", 0.25)):
        ledger.insert("decisions", {"id": decision, "kind": "lp_quote", "ticker": "S-E1-A", "created_ts": now(), "mode": "shadow",
                                    "strategy": "lp", "action": "order", "reasons": ["reward_day=0.750", "share=0.010"]})
        broker.place(decision, "S-E1-A", "yes", price, 10, 3600)
    ledger.insert("fills", {"id": new_id(), "client_order_id": client_order_id("d1"), "ticker": "S-E1-A", "side": "yes",
                            "price": 0.40, "contracts": 10, "fee": 0.0, "ts": now(), "simulated": True})
    ledger.execute("UPDATE orders SET status='filled' WHERE client_order_id=?", [client_order_id("d1")])
    for i, equity in enumerate((1000.0, 999.5, 999.0)):
        ledger.insert("equity_history", {"mode": "shadow", "ts": now() - 600 * (2 - i), "cash": 996.0, "positions_value": equity - 996.0,
                                         "equity": equity, "resting_at_risk": 2.5, "estimated_rewards": 0.1 * i, "credited": None})
    return ledger


def test_dashboard_shows_positions_quotes_fills_and_history():
    data = collect(seeded(), config.load("config/settings.yaml"))
    (position,) = data["positions"]
    assert (position["cost"], round(position["value"], 2), position["priced"]) == (4.0, 3.0, True)   # 10 contracts marked at 30c
    (quote,) = data["resting"]
    assert (quote["price"], quote["contracts"], quote["reward_day"]) == (0.25, 10, 0.75)
    assert data["fills_total"] == 1 and len(data["series"]) == 3 and data["latest"]["equity"] == 999.0
    page = render(data)
    assert "<b>it</b>" not in page.split('id="data">')[0]         # market text is only ever inserted as text, never as markup
    assert json.loads(page.split('id="data">')[1].split("</script>")[0])["mode"] == "shadow"


def test_dashboard_builds_for_an_empty_account():
    page = render(collect(Ledger(":memory:"), config.load("config/settings.yaml")))
    assert "pmbot · paper" in page
