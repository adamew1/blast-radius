"""Dependency graph primitives.

A position is the root. Edges point parent -> child ("parent depends on child").
A failure in a child propagates UP to its parents (see risk/propagate.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import networkx as nx

NODE_KINDS = {
    "position", "protocol", "token", "oracle", "chain",
    "amm", "lending_market", "issuer", "custodian",
}
EDGE_TYPES = {"backing", "collateral", "oracle", "liquidity", "chain", "issuer"}

# Where an edge's fact came from (drives the UI "manual"/"reconstructed" badges).
SOURCE_API = "api"            # prefix, e.g. "api:pendle"
SOURCE_MANUAL = "manual"
SOURCE_RECONSTRUCTED = "reconstructed"


@dataclass
class Node:
    id: str
    kind: str
    label: str
    chain: Optional[str] = None
    price_key: Optional[str] = None       # DefiLlama coin key, if the node is priceable
    meta: dict = field(default_factory=dict)


@dataclass
class Edge:
    parent: str
    child: str
    dep_type: str
    exposure_pct: float = 100.0           # % of the parent's value exposed to this child
    source: str = SOURCE_MANUAL           # 'api:pendle' | 'api:morpho' | 'api:defillama' | 'manual' | 'reconstructed'
    confidence: float = 1.0
    note: str = ""

    @property
    def is_manual(self) -> bool:
        return self.source in (SOURCE_MANUAL, SOURCE_RECONSTRUCTED)


class DependencyGraph:
    def __init__(self, root_id: str):
        self.g = nx.DiGraph()
        self.root_id = root_id

    # --- mutation ---
    def add_node(self, node: Node) -> None:
        if node.id in self.g and self.g.nodes[node.id].get("obj"):
            return  # keep first definition
        self.g.add_node(node.id, obj=node)

    def add_edge(self, edge: Edge) -> None:
        self.g.add_edge(edge.parent, edge.child, obj=edge)

    # --- access ---
    def node(self, nid: str) -> Node:
        return self.g.nodes[nid]["obj"]

    def edge(self, u: str, v: str) -> Edge:
        return self.g.edges[u, v]["obj"]

    def has_node(self, nid: str) -> bool:
        return nid in self.g

    def nodes(self) -> list[Node]:
        return [self.g.nodes[n]["obj"] for n in self.g.nodes]

    def edges(self) -> list[Edge]:
        return [self.g.edges[u, v]["obj"] for u, v in self.g.edges]

    def children(self, nid: str) -> list[str]:
        return list(self.g.successors(nid))

    def parents(self, nid: str) -> list[str]:
        return list(self.g.predecessors(nid))

    def descendants(self, nid: str) -> set[str]:
        return set(nx.descendants(self.g, nid))

    def topo_order(self) -> list[str]:
        """Children before parents (so shocks can be accumulated upward in one pass)."""
        return list(reversed(list(nx.topological_sort(self.g))))

    def to_payload(self) -> dict:
        """Plain dict for the Streamlit layer."""
        return {
            "root": self.root_id,
            "nodes": [vars(n) for n in self.nodes()],
            "edges": [vars(e) for e in self.edges()],
        }
