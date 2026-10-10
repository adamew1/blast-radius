"""Minimal, identical-shape dependency graph for one backtest event.

Exactly the structure the brief specifies: the downstream holding (the position) depends on the
upstream asset via one typed, weighted edge. Loss propagates from the forced upstream up to the
position through the SAME engine used in production (no special-casing).

    position(downstream $1M) --[dep_type, exposure_pct]--> upstream(forced leaf)
"""
from __future__ import annotations

from ..discovery.graph import DependencyGraph, Edge, Node

# Low-hazard categories for the two nodes so that, in calm windows (upstream NOT forced), the
# intrinsic baseline EL stays well under the 1% exit cost — the signal is driven by the forced
# upstream shock, not by model noise. These are the real DefiLlama/prior categories for the asset.
UPSTREAM_ID = "upstream"
POSITION_ID = "position"


def build_event_graph(event: dict) -> DependencyGraph:
    g = DependencyGraph(root_id=POSITION_ID)
    g.add_node(Node(id=POSITION_ID, kind="position",
                    label=f"Holding: {event['downstream']['label']}", chain="ethereum",
                    meta={"risk_category": None, "apy": 0.0, "size_usd": 1_000_000}))
    g.add_node(Node(id=UPSTREAM_ID, kind="token", label=event["upstream"]["label"], chain="ethereum",
                    meta={"risk_category": "Stablecoin (fiat)"}))
    g.add_edge(Edge(parent=POSITION_ID, child=UPSTREAM_ID, dep_type=event["dep_type"],
                    exposure_pct=float(event["exposure_pct"]), source="reconstructed",
                    note=event.get("exposure_source", "")))
    return g
