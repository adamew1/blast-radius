"""Candidate exits with explicit quote availability and shared market resources."""
from __future__ import annotations

import json
import math
from pathlib import Path

from ..config import ROOT
from .model import Portfolio

BUNDLE = ROOT / "data/fire_drill/execution.json"


def load_execution(path: Path = BUNDLE) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"positions": {}}


def exit_options(book: Portfolio, bundle: dict | None = None, carry_days: int = 30) -> dict:
    bundle = bundle if bundle is not None else load_execution()
    options, resources, vault_caps, unavailable = {}, {}, {}, []
    for p in book.positions:
        pid = p["id"]
        apy = book.graphs[pid].node(book.graphs[pid].root_id).meta.get("apy", 0) or 0
        options[pid] = [{"fraction": 0.0, "notional_usd": 0.0, "execution_usd": 0.0,
                         "conversion_usd": 0.0, "carry_usd": 0.0, "source": "hold"}]
        caps = {}
        if p["kind"] == "morpho_vault":
            for a in book.vaults[pid].get("state", {}).get("allocation", []):
                m = a.get("market") or {}
                supply = float(a.get("supplyAssetsUsd") or 0)
                liquidity = (m.get("state") or {}).get("liquidityAssetsUsd")
                if supply <= 0 or liquidity is None or not math.isfinite(float(liquidity)):
                    continue
                mid = m["marketId"]
                cap = min(supply, max(0, float(liquidity)))
                caps[mid] = caps.get(mid, 0) + cap
                resources[mid] = min(resources.get(mid, float("inf")), max(0, float(liquidity)))
            vault_caps[pid] = caps
        record = bundle.get("positions", {}).get(pid, {})
        recorded = {round(o["fraction"], 8): o for o in record.get("options", [])}
        if record and record.get("position") != p:
            recorded = {}  # never apply another size's quote grid to this position
        for step in range(1, 21):
            fraction = step / 20
            notional = p["size_usd"] * fraction
            if p["kind"] == "pendle_pt":
                q = recorded.get(round(fraction, 8))
                if not q or not q.get("available"):
                    unavailable.append({"position": pid, "fraction": fraction,
                                        "reason": (q or {}).get("error", "No captured quote")})
                    continue
                if abs(q["notional_usd"] - notional) > .01:
                    raise ValueError("Quote notional differs from candidate")
                execution = q["mark_shortfall_usd"] + notional * .0002
                source = q["raw_cache_key"]
            elif p["kind"] == "morpho_vault":
                if notional > sum(caps.values()) + .001:
                    unavailable.append({"position": pid, "fraction": fraction,
                                        "reason": "Exceeds vault snapshot liquidity bound"})
                    continue
                execution = notional * .0002
                source = "cached Morpho funded allocations and market liquidity"
            else:
                raise ValueError(f"Unsupported position kind {p['kind']}")
            options[pid].append({"fraction": fraction, "notional_usd": notional,
                                 "execution_usd": execution, "conversion_usd": notional * .001,
                                 "carry_usd": notional * max(0, apy) * carry_days / 365,
                                 "source": source})
    return {"options": options, "resources": resources, "vault_caps": vault_caps,
            "unavailable": unavailable, "carry_days": carry_days,
            "gas_bps_assumed": 2, "conversion_bps_assumed": 10}
