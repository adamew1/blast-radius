"""Repo paths and config loader."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
MANUAL = DATA / "manual"
REPLAY = DATA / "replay"
BOOK = DATA / "book"
ARTIFACTS = ROOT / "artifacts"


@lru_cache(maxsize=1)
def load_config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def manual_map() -> dict:
    p = MANUAL / "dependencies.yaml"
    if not p.exists():
        return {"tokens": {}}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {"tokens": {}}
