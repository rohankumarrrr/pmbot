"""One-time setup of a ring-fenced Kalshi subaccount for the bot.

Given an API key for the whole account (the "setup key"), this:
  1. makes sure the account may create subaccounts (Advanced API tier; see --qualifying-order),
  2. creates a subaccount, or uses the one named with --subaccount,
  3. moves the test bankroll into it from the primary account,
  4. creates a new API key that can only read and trade inside that subaccount,
  5. checks the new key sees the subaccount and nothing else, and
  6. with --delete-setup-key, deletes the setup key so no credential for the whole account remains.

The bot then runs on the restricted key: whatever it does, it cannot reach the rest of the account.

  python scripts/setup_subaccount.py --env demo --setup-creds ~/.config/pmbot/demo --out /tmp/sub --amount 50
  python scripts/setup_subaccount.py --env prod --setup-creds ~/.config/pmbot/setup --out ~/.config/pmbot/live \\
         --amount 100 --delete-setup-key

Nothing here places an order unless --qualifying-order is given. Kalshi grants the Advanced tier only to
accounts with an API-created order among their last 100; that flag places one post-only bid for a single
contract at 1 cent in a market trading far above it, and cancels it at once.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pmbot.kalshi.client import DEMO, PROD, KalshiClient, KalshiError, dollars

BOT_SCOPES = ["read", "write::trade"]      # no transfers, no key management


def say(*a) -> None:
    print(*a, flush=True)


def client_from(env: str, creds: Path) -> KalshiClient:
    return KalshiClient.from_key_file(DEMO if env == "demo" else PROD, (creds / "key_id").read_text().strip(), creds / "private_key.pem")


def balances(c: KalshiClient) -> dict[int, float]:
    """Dollars per subaccount on the default exchange shard (index 0), where the reward markets trade.
    Kalshi keeps a separate balance per shard; combos, crypto and some sports live on others."""
    return {int(r["subaccount_number"]): dollars(r["balance"])
            for r in c.get("/portfolio/subaccounts/balances", auth=True).get("subaccount_balances") or []
            if int(r.get("exchange_index") or 0) == 0}


def ensure_tier(c: KalshiClient, env: str, qualifying_order: bool) -> None:
    tier = c.get("/account/limits", auth=True).get("usage_tier")
    say(f"API usage tier: {tier}")
    if tier != "basic" or env == "demo":       # demo does not enforce the tier
        return
    try:
        c.request("POST", "/account/api_usage_level/upgrade", auth=True, retry=False)
    except KalshiError as e:
        if e.status != 403:
            raise
        if not qualifying_order:
            sys.exit("Kalshi will not grant the Advanced tier yet: none of the account's last 100 orders was "
                     "placed through the API. Re-run with --qualifying-order to place and cancel one 1-cent order.")
        place_qualifying_order(c)
        for attempt in range(6):                # the order can take a moment to count
            try:
                c.request("POST", "/account/api_usage_level/upgrade", auth=True, retry=False)
                break
            except KalshiError as e2:
                if e2.status != 403 or attempt == 5:
                    raise
                time.sleep(10)
    say("API usage tier now:", c.get("/account/limits", auth=True).get("usage_tier"))


def place_qualifying_order(c: KalshiClient) -> None:
    """A post-only bid for 1 contract at 1 cent where the best bid is far higher: it cannot trade."""
    for ev in c.events(status="open", with_nested_markets=True):
        for m in ev.get("markets") or []:
            if (m.get("status") == "active" and not m.get("exchange_index") and m.get("market_type") == "binary"
                    and dollars(m.get("yes_bid_dollars")) >= 0.30 and dollars(m.get("yes_ask_dollars")) <= 0.90):
                coid = f"pm-setup-{uuid.uuid4().hex[:12]}"
                order = c.create_order(m["ticker"], "bid", 1, 0.01, coid, post_only=True, expiration_ts=int(time.time()) + 120)
                c.cancel_order(order["order_id"])
                say(f"placed and cancelled one 1-cent post-only bid on {m['ticker']} (best bid {m.get('yes_bid_dollars')})")
                return
    sys.exit("found no suitable market for the qualifying order")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", choices=["demo", "prod"], required=True)
    ap.add_argument("--setup-creds", type=Path, required=True, help="directory holding key_id and private_key.pem for the whole account")
    ap.add_argument("--out", type=Path, required=True, help="directory to write the restricted key to")
    ap.add_argument("--amount", type=float, required=True, help="dollars the subaccount should hold")
    ap.add_argument("--subaccount", type=int, help="use this existing subaccount instead of creating one")
    ap.add_argument("--fund-only", action="store_true", help="only move money into --subaccount (its key already exists)")
    ap.add_argument("--qualifying-order", action="store_true")
    ap.add_argument("--delete-setup-key", action="store_true")
    a = ap.parse_args()
    setup_creds, out = a.setup_creds.expanduser(), a.out.expanduser()
    if a.fund_only and a.subaccount is None:
        sys.exit("--fund-only needs --subaccount")
    if (out / "key_id").exists() and not a.fund_only:
        sys.exit(f"{out}/key_id already exists; refusing to overwrite a key")

    c = client_from(a.env, setup_creds)
    before = balances(c)
    say("balances before:", {k: f"${v:.2f}" for k, v in sorted(before.items())})
    if before.get(0, 0.0) < a.amount and a.subaccount is None:
        sys.exit(f"the primary account holds ${before.get(0, 0.0):.2f}, less than the ${a.amount:.2f} to move")

    sub = a.subaccount
    if sub is None:
        ensure_tier(c, a.env, a.qualifying_order)
        sub = int(c.request("POST", "/portfolio/subaccounts", json={}, auth=True, retry=False)["subaccount_number"])
        say(f"created subaccount {sub}")
    elif sub not in before:
        sys.exit(f"subaccount {sub} does not exist")

    shortfall = round(a.amount - balances(c).get(sub, 0.0), 2)
    if shortfall > 0:
        if balances(c).get(0, 0.0) < shortfall:
            sys.exit(f"the primary account holds less than the ${shortfall:.2f} still to move")
        c.request("POST", "/portfolio/subaccounts/transfer", auth=True, retry=False, json={
            "client_transfer_id": str(uuid.uuid4()), "from_subaccount": 0, "to_subaccount": sub,
            "amount_cents": int(round(shortfall * 100)), "exchange_index": 0})
        say(f"moved ${shortfall:.2f} from the primary account to subaccount {sub}")
    after = balances(c)
    say("balances after: ", {k: f"${v:.2f}" for k, v in sorted(after.items())})

    if a.fund_only:
        if a.delete_setup_key:
            c.request("DELETE", f"/api_keys/{c.key_id}", auth=True, retry=False)
            say("deleted the setup key: no credential for the whole account remains with the bot")
        return

    key = Ed25519PrivateKey.generate()
    public_pem = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    made = c.request("POST", "/api_keys", auth=True, retry=False, json={
        "name": f"pmbot subaccount {sub}", "public_key": public_pem, "scopes": BOT_SCOPES, "subaccount": sub})
    out.mkdir(parents=True, exist_ok=True)
    out.chmod(0o700)
    (out / "key_id").write_text(made["api_key_id"] + "\n")
    (out / "private_key.pem").write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    for f in ("key_id", "private_key.pem"):
        (out / f).chmod(0o600)
    say(f"created a key restricted to subaccount {sub} with scopes {BOT_SCOPES}; saved in {out}")

    bot = client_from(a.env, out)
    bot.subaccount = sub
    seen = dollars(bot.balance().get("balance_dollars"))
    say(f"restricted key sees ${seen:.2f} in subaccount {sub}")
    try:
        bot.get("/portfolio/balance", auth=True, subaccount=0)
        say("WARNING: the restricted key could read the primary account's balance")
    except KalshiError as e:
        say(f"restricted key is refused the primary account ({e.status}): as intended")
    try:
        bot.request("POST", "/portfolio/subaccounts/transfer", auth=True, retry=False, json={
            "client_transfer_id": str(uuid.uuid4()), "from_subaccount": 0, "to_subaccount": sub, "amount_cents": 1})
        say("WARNING: the restricted key was able to move money between subaccounts")
    except KalshiError as e:
        say(f"restricted key is refused transfers ({e.status}): as intended")

    if a.delete_setup_key:
        c.request("DELETE", f"/api_keys/{c.key_id}", auth=True, retry=False)
        say("deleted the setup key: no credential for the whole account remains with the bot")
    say(f"\nDone. Set kalshi.subaccount: {sub} in the bot's config.")


if __name__ == "__main__":
    main()
