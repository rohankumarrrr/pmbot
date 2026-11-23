"""Settings changed while a bot runs.

The reward strategy's settings (`lp.*`) can be changed from the command line and take effect on the
bot's next cycle, with no deploy and no restart:

    pmbot set lp.max_markets_per_family 2 --why "one family filled four times today"
    pmbot pause KXAAAGAS --why "answer is published on a schedule"
    pmbot unset lp.max_markets_per_family
    pmbot settings

Changes are kept in the bot's own ledger, so each bot (paper, demo, twin, live) has its own, and every
change is written to the risk-event log with its reason. A change made this way is an experiment: once
it has earned its place, put it in the config file and unset it here.

The hard limits are not adjustable here. They are changed in the config file, by Rohan.
"""

from __future__ import annotations

from typing import Any

import yaml

from .config import Config
from .ledger.db import Ledger

# Rohan's limits and the switches that decide whether the strategy runs at all.
LOCKED = {"capital_fraction", "max_at_risk_per_quote", "enabled", "synthetic_programs"}


def _key(mode: str) -> str:
    return f"overrides:{mode}"


def name_of(setting: str) -> str:
    """'lp.requote_ticks' or 'requote_ticks' -> 'requote_ticks'. Only reward-strategy settings are adjustable."""
    section, _, name = setting.rpartition(".")
    if section not in ("", "lp"):
        raise ValueError(f"only lp.* settings can be changed while the bot runs, not {setting!r}")
    return name


def parse(text: str) -> Any:
    """A value typed on the command line: 2, 0.35, true, [KXAAAGAS, KXTRUMP], [[0.15, -0.45], [0.50, -0.35]]."""
    return yaml.safe_load(text)


def _same_kind(old: Any, new: Any) -> bool:
    number = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    if number(old):
        return number(new)
    return type(old) is type(new)


def check(base: dict, name: str, value: Any) -> None:
    """Raise ValueError unless `name` is an adjustable reward-strategy setting and `value` fits it."""
    if name in LOCKED:
        raise ValueError(f"lp.{name} is a hard limit: change it in the config file, not at run time")
    if name not in base:
        raise ValueError(f"lp.{name} is not a setting (known: {', '.join(sorted(k for k in base if k not in LOCKED))})")
    if not _same_kind(base[name], value):
        raise ValueError(f"lp.{name} is {base[name]!r}; {value!r} is a different kind of value")


def load(ledger: Ledger, mode: str) -> dict:
    return dict(ledger.get_state(_key(mode)) or {})


def put(ledger: Ledger, mode: str, base: dict, setting: str, value: Any, why: str = "") -> Any:
    """Set one override. Returns the value that was in effect before."""
    name = name_of(setting)
    check(base, name, value)
    current = load(ledger, mode)
    before = current.get(name, base[name])
    current[name] = value
    ledger.set_state(_key(mode), current)
    ledger.risk_event("setting_changed", f"lp.{name}: {before!r} -> {value!r}" + (f" ({why})" if why else ""))
    return before


def drop(ledger: Ledger, mode: str, base: dict, setting: str, why: str = "") -> bool:
    """Remove one override, going back to the config file's value. Returns whether there was one."""
    name = name_of(setting)
    current = load(ledger, mode)
    if name not in current:
        return False
    was = current.pop(name)
    ledger.set_state(_key(mode), current)
    ledger.risk_event("setting_changed", f"lp.{name}: {was!r} -> {base.get(name)!r}, back to the config file"
                      + (f" ({why})" if why else ""))
    return True


def effective(base: dict, ledger: Ledger, mode: str) -> Config:
    """The reward-strategy settings in force now: the config file's, with the run-time changes on top.

    A stored change that no longer fits (the setting was renamed, or became a hard limit) is ignored.
    """
    out = dict(base)
    for name, value in load(ledger, mode).items():
        try:
            check(base, name, value)
        except ValueError:
            continue
        out[name] = value
    return Config(out)


def pause(ledger: Ledger, mode: str, base: dict, prefix: str, why: str = "") -> list[str]:
    """Stop quoting every market whose ticker starts with `prefix`; resting quotes there are pulled next cycle."""
    families = list(effective(base, ledger, mode).get("exclude_families") or [])
    if prefix not in families:
        families.append(prefix)
        put(ledger, mode, base, "exclude_families", families, why or f"pause {prefix}")
    return families


def unpause(ledger: Ledger, mode: str, base: dict, prefix: str, why: str = "") -> list[str]:
    families = [f for f in (effective(base, ledger, mode).get("exclude_families") or []) if f != prefix]
    if families == list(base.get("exclude_families") or []):
        drop(ledger, mode, base, "exclude_families", why or f"unpause {prefix}")
    else:
        put(ledger, mode, base, "exclude_families", families, why or f"unpause {prefix}")
    return families
