"""Load the frozen signal rule + event library (declared before any event was run)."""
from __future__ import annotations

import pathlib
from functools import lru_cache

import yaml

_BT = pathlib.Path(__file__).resolve().parents[2] / "data" / "backtest"


@lru_cache(maxsize=1)
def load_rule() -> dict:
    return yaml.safe_load((_BT / "signal_rule.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_events() -> dict:
    return yaml.safe_load((_BT / "events.yaml").read_text(encoding="utf-8"))


def events() -> list[dict]:
    return load_events()["events"]


def denom_keys() -> dict:
    return load_events().get("denom_keys", {})
