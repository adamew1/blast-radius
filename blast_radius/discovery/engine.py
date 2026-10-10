"""Recursive look-through engine: build the full dependency graph for a position.

The 5-layer Pendle example is NOT hard-coded — it falls out of generic recursion:
position -> (settlement chain, PT AMM, underlying, lending markets holding the PT) and then
the underlying token unwraps through its backing -> issuer -> oracle -> base asset -> chain.
"""
from __future__ import annotations

from collections import deque

from .graph import DependencyGraph, Node
from .resolvers import Context, resolve_morpho_vault, resolve_pendle_pt, resolve_token

_RESOLVERS = {
    "pendle_pt": resolve_pendle_pt,
    "morpho_vault": resolve_morpho_vault,
}


def build_graph(position: dict, max_depth: int = 8) -> DependencyGraph:
    cid = position.get("chain_id", 1)
    ctx = Context(chain_id=cid, chain_name=position.get("chain", "ethereum"))

    g = DependencyGraph(root_id=f"pos:{position['id']}")
    root = Node(id=g.root_id, kind="position", label=position["label"], chain=position.get("chain"),
                meta={"pos_kind": position["kind"], "size_usd": position.get("size_usd", 0)})
    g.add_node(root)

    resolver = _RESOLVERS.get(position["kind"])
    if resolver is None:
        raise ValueError(f"no resolver for position kind {position['kind']!r}")
    frontier = [(nid, 1) for nid in resolver(g, root, ctx, position)]

    queue = deque(frontier)
    visited = {g.root_id}
    while queue:
        nid, depth = queue.popleft()
        if nid in visited:
            continue
        visited.add(nid)
        node = g.node(nid)
        if node.kind == "token" and depth < max_depth:
            for child in resolve_token(g, node, ctx):
                if child not in visited:
                    queue.append((child, depth + 1))
    return g


def summarize(g: DependencyGraph) -> dict:
    """Quick structural summary (counts by kind / dependency type / source)."""
    by_kind: dict[str, int] = {}
    for n in g.nodes():
        by_kind[n.kind] = by_kind.get(n.kind, 0) + 1
    by_type: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for e in g.edges():
        by_type[e.dep_type] = by_type.get(e.dep_type, 0) + 1
        src = "manual" if e.is_manual else e.source.split(":")[0]
        by_source[src] = by_source.get(src, 0) + 1
    return {"nodes": len(g.nodes()), "edges": len(g.edges()),
            "by_kind": by_kind, "by_dep_type": by_type, "by_source": by_source}
