"""Explicit, frozen Ethereum instrument universe; no arbitrary address imports."""
from __future__ import annotations

import json

from ..config import ROOT
from ..portfolio.book import load_book
from .execution import load_execution

CATALOG = ROOT / "data/fire_drill/catalog.json"
QUOTES = ROOT / "data/fire_drill/catalog_execution.json"


def load_catalog() -> list[dict]:
    positions = load_book()["positions"]
    if CATALOG.exists():
        document = json.loads(CATALOG.read_text(encoding="utf-8"))
        if document.get("schema") != "blast-radius-catalog-v1" or document.get("chain_id") != 1:
            raise ValueError("Unsupported catalog schema or chain")
        positions += document["positions"]
    identities, ids = set(), set()
    for position in positions:
        kind = position["kind"]
        if kind not in ("pendle_pt", "morpho_vault") or position["chain_id"] != 1 or position["chain"] != "ethereum":
            raise ValueError("Catalog supports only the admitted Ethereum PT markets and vaults")
        address = position["market" if kind == "pendle_pt" else "vault"].lower()
        identity = (kind, address)
        if identity in identities or position["id"] in ids:
            raise ValueError("Duplicate catalog instrument")
        identities.add(identity)
        ids.add(position["id"])
    return positions


def execution_for(positions: list[dict]) -> dict:
    """Keep the original bundle intact; add independently captured PT records."""
    bundle = load_execution()
    new_pt = {p["id"] for p in positions if p["kind"] == "pendle_pt"} - bundle["positions"].keys()
    if new_pt:
        extra = json.loads(QUOTES.read_text(encoding="utf-8"))
        if new_pt - extra["positions"].keys():
            raise ValueError("No frozen execution evidence for this PT market")
        bundle["positions"].update(extra["positions"])
        bundle["catalog_rpc"] = {k: extra[k] for k in ("rpc", "rpc_block", "rpc_block_timestamp")}
    return bundle
