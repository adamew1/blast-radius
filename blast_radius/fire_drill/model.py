"""Single-event stress. Alternate paths overlap; funded allocations are disjoint.

This deliberately does not reuse multiplicative independent-event survival for a
single shared failure. A wrapper uses its strongest transmission channel. A vault
adds explicitly funded allocation losses. Lending collateral uses incremental
aggregate shortfall, not LLTV as a proxy for supplier loss.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import networkx as nx

from ..discovery.engine import build_graph
from ..discovery.graph import DependencyGraph
from ..models.passthrough import pass_through
from ..sources import morpho
from . import MODEL_VERSION


@dataclass
class Portfolio:
    positions: list[dict]
    graphs: dict[str, DependencyGraph]
    vaults: dict[str, dict]


def prepare(positions: list[dict]) -> Portfolio:
    if not positions or len({p["id"] for p in positions}) != len(positions):
        raise ValueError("A nonempty book with unique position ids is required")
    if any(not math.isfinite(p["size_usd"]) or p["size_usd"] <= 0 for p in positions):
        raise ValueError("Position sizes must be finite and positive")
    graphs, vaults = {}, {}
    for p in positions:
        graphs[p["id"]] = build_graph(p)
        if p["kind"] == "morpho_vault":
            vaults[p["id"]] = morpho.vault_by_address(p["vault"], p.get("chain_id", 1))
    return Portfolio(positions, graphs, vaults)


def shortfall_loss(state: dict, shock: float) -> float:
    """Incremental supplier loss assuming immediate aggregate collateral recovery."""
    values = [state.get(k) for k in ("supplyAssetsUsd", "borrowAssetsUsd", "collateralAssetsUsd")]
    if any(v is None or not math.isfinite(float(v)) or float(v) < 0 for v in values):
        raise ValueError("Incomplete or invalid lending-market balance sheet")
    supply, debt, collateral = map(float, values)
    if supply <= 0:
        return 0.0
    baseline = max(0.0, debt - collateral)
    stressed = max(0.0, debt - collateral * (1.0 - shock))
    return min(1.0, max(0.0, (stressed - baseline) / supply))


def stress_graph(g: DependencyGraph, dependency_id: str, severity: float,
                 vault: dict | None = None) -> dict:
    """Return all node losses and contributing actual edges for one position."""
    if not math.isfinite(severity) or not 0 <= severity <= 1:
        raise ValueError("Severity must lie in [0, 1]")
    allocation = {f"lmkt:morpho:{a['market']['marketId']}": a
                  for a in (vault or {}).get("state", {}).get("allocation", [])
                  if a.get("market", {}).get("marketId")}
    total_assets = (vault or {}).get("state", {}).get("totalAssetsUsd", 0) or 0
    losses, flows, rules = {}, {}, {}
    for nid in g.topo_order():
        n = g.node(nid)
        branches = []
        for child in sorted(g.children(nid)):
            e = g.edge(nid, child)
            coefficient = pass_through(e.dep_type)
            # PT redemption is denominated in its underlying. A generic backing
            # haircut would manufacture residual value after a worthless claim.
            # The deterministic model holds the PT discount factor fixed, so its
            # USD mark scales one-for-one with the underlying mark.
            pt_claim = e.dep_type == "backing" and (n.meta.get("pt") or n.meta.get("is_pendle_pt"))
            if pt_claim:
                coefficient = 1.0
            contribution = losses[child] * coefficient * e.exposure_pct / 100
            rule = "PT underlying-denominated claim, fixed discount factor" if pt_claim else "strongest overlapping channel"
            # Funded allocations are separate claims. Use exact API weights,
            # rather than rounded graph labels or the generic collateral haircut.
            if nid == g.root_id and child in allocation and total_assets > 0:
                coefficient = allocation[child].get("supplyAssetsUsd", 0) / total_assets
                contribution = losses[child] * coefficient
                rule = "disjoint funded allocation"
            # Supplier losses arise after collateral recovery cannot cover debt.
            if n.kind == "lending_market" and nid in allocation and e.dep_type == "collateral":
                contribution = shortfall_loss(allocation[nid]["market"].get("state") or {}, losses[child])
                coefficient = None
                rule = "incremental aggregate collateral shortfall / market supply"
            branches.append((child, max(0.0, min(1.0, contribution)), rule, coefficient))
        intrinsic = severity if nid == dependency_id else 0.0
        funded = sum(x[1] for x in branches if x[2] == "disjoint funded allocation")
        other = max((x[1] for x in branches if x[2] != "disjoint funded allocation"), default=0.0)
        value = min(1.0, max(intrinsic, funded, other))
        losses[nid] = value
        rules[nid] = "funded allocation sum" if funded > other else "strongest channel"
        # Only retain the channels used by this computation. Ties choose a
        # canonical edge, so duplicate alternate paths do not create extra flow.
        if intrinsic >= max(funded, other) and intrinsic > 0:
            continue
        if funded >= other and funded > 0:
            active = [x for x in branches if x[2] == "disjoint funded allocation" and x[1] > 0]
        else:
            active = [x for x in branches if x[1] == other and other > 0][:1]
        for child, amount, rule, coefficient in active:
            flows[(nid, child)] = {"fraction_at_parent": amount, "rule": rule,
                                   "coefficient": coefficient}
    # Project root loss dollars down selected dependency channels. This is
    # explanatory attribution, not a claim that dollars at intermediate nodes add.
    path_flows = {}
    amounts = {g.root_id: losses[g.root_id]}
    for nid in nx.topological_sort(g.g):
        active = [(c, flows[(nid, c)]) for c in g.children(nid) if (nid, c) in flows]
        denominator = sum(f["fraction_at_parent"] for _, f in active)
        for child, flow in active:
            attributed = amounts.get(nid, 0.0) * flow["fraction_at_parent"] / denominator if denominator else 0
            amounts[child] = amounts.get(child, 0.0) + attributed
            if attributed > 0:
                path_flows[(nid, child)] = {**flow, "root_loss_fraction": attributed}
    return {"fraction": losses[g.root_id], "node_losses": losses,
            "flows": path_flows, "rules": rules}


def stress_book(book: Portfolio, dependency_id: str, severity: float = 1.0) -> dict:
    if not any(g.has_node(dependency_id) for g in book.graphs.values()):
        raise ValueError("Unknown dependency")
    rows, affected, total = [], 0.0, 0.0
    for p in book.positions:
        g = book.graphs[p["id"]]
        r = stress_graph(g, dependency_id, severity, book.vaults.get(p["id"]))
        exposed = g.has_node(dependency_id)
        loss = r["fraction"] * p["size_usd"]
        affected += p["size_usd"] if exposed else 0
        total += p["size_usd"]
        rows.append({"id": p["id"], "label": p["label"], "size_usd": p["size_usd"],
                     "fraction": r["fraction"], "loss_usd": loss, "exposed": exposed,
                     "apy": g.node(g.root_id).meta.get("apy", 0) or 0,
                     "node_losses": r["node_losses"],
                     "flows": [{"parent": u, "child": v, **flow,
                                "impact_usd": flow["root_loss_fraction"] * p["size_usd"]}
                               for (u, v), flow in r["flows"].items()]})
    return {"model_version": MODEL_VERSION, "dependency_id": dependency_id, "severity": severity,
            "aum_usd": total, "affected_capital_usd": affected,
            "exposed_positions": sum(r["exposed"] for r in rows),
            "loss_usd": sum(r["loss_usd"] for r in rows), "positions": rows}


def discover(book: Portfolio) -> list[dict]:
    nodes = {n.id: n for g in book.graphs.values() for n in g.nodes() if n.kind != "position"}
    result = []
    for nid, n in nodes.items():
        s = stress_book(book, nid, 1.0)
        result.append({"id": nid, "label": n.label, "kind": n.kind,
                       "positions": s["exposed_positions"], "loss_usd": s["loss_usd"],
                       "affected_capital_usd": s["affected_capital_usd"],
                       "exposure_concentration": s["affected_capital_usd"] / s["aum_usd"],
                       "conditional_loss_pct": s["loss_usd"] / s["aum_usd"]})
    return sorted(result, key=lambda r: (-r["loss_usd"], -r["positions"], r["id"]))
