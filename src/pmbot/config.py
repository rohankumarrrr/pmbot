from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PATH = Path(os.environ.get("PMBOT_CONFIG", "config/settings.yaml"))


class Config(dict):
    """Nested dict with attribute access: cfg.trading.min_edge."""

    def __getattr__(self, name: str) -> Any:
        try:
            v = self[name]
        except KeyError as e:
            raise AttributeError(name) from e
        return Config(v) if isinstance(v, dict) else v


def merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load(path: str | Path | None = None) -> Config:
    """A file may name a base with `extends:` and list only the settings it changes."""
    path = Path(path or DEFAULT_PATH)
    raw = yaml.safe_load(path.read_text())
    if "extends" in raw:
        raw = merge(dict(load(path.parent / raw.pop("extends"))), raw)
    cfg = Config(raw)
    if cfg["mode"] not in ("shadow", "demo", "live"):
        raise ValueError(f"mode must be shadow, demo or live, not {cfg['mode']!r}")
    return cfg
