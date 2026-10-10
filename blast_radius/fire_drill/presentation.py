"""Stable, compact view retaining actual paths and per-position attribution."""
from __future__ import annotations

import networkx as nx

from .model import Portfolio


def network(book: Portfolio, ranking: list[dict], stress: dict, revealed: bool,
            attacked: bool, plan: dict | None = None) -> dict:
    all_nodes = {n.id: n for g in book.graphs.values() for n in g.nodes()}
    selected = stress["dependency_id"]
    by_pos = {r["id"]: r for r in stress["positions"]}
    fractions = {a["id"]: a["fraction"] for a in (plan or {}).get("actions", [])}
    selected_paths = {p["id"]: list(nx.all_simple_paths(book.graphs[p["id"]].g,
                      book.graphs[p["id"]].root_id, selected))
                      if book.graphs[p["id"]].has_node(selected) else [] for p in book.positions}
    intermediates_in_selection = {nid for paths in selected_paths.values() for path in paths for nid in path[1:-1]}
    collapse_selection = len(intermediates_in_selection) > 12
    # Overview selects issuer dependencies, plus the current selection. Each
    # visual link retains all actual path ids for inspection and expansion.
    featured = [r["id"] for r in ranking if r["kind"] == "issuer"][:10]
    if selected not in featured:
        featured = [selected] + featured[:9]
    edges, nodes = [], []
    for i, nid in enumerate(featured):
        n = all_nodes[nid]
        row = next(r for r in ranking if r["id"] == nid)
        nodes.append({"id": nid, "label": n.label, "kind": n.kind, "column": 0, "row": i,
                      "meta": n.meta, "count": row["positions"], "source": n.meta.get("source"),
                      "selected": nid == selected})
    for i, p in enumerate(book.positions):
        g = book.graphs[p["id"]]
        r = by_pos[p["id"]]
        nodes.append({"id": g.root_id, "label": p["label"], "kind": "position", "column": 3,
                      "row": i, "size_usd": p["size_usd"], "loss_usd": r["loss_usd"] if attacked else 0,
                      "remaining_loss_usd": r["loss_usd"] * (1 - fractions.get(p["id"], 0)),
                      "sold_fraction": fractions.get(p["id"], 0), "position_id": p["id"]})
        if not revealed:
            continue
        for nid in featured:
            if not g.has_node(nid):
                continue
            paths = selected_paths[p["id"]] if nid == selected else list(nx.all_simple_paths(g.g, g.root_id, nid))
            if nid != selected or collapse_selection:
                impact = r["loss_usd"] if nid == selected and attacked else 0
                edges.append({"parent": g.root_id, "child": nid, "impact_usd": impact,
                              "remaining_impact_usd": impact * (1 - fractions.get(p["id"], 0)),
                              "active": impact > 0, "collapsed": True, "paths": paths,
                              "position": p["id"]})
                continue
            used = {(f["parent"], f["child"]): f for f in r["flows"]}
            # Show active numerical paths if attacked; otherwise expose the
            # discovered paths. Include dormant structural paths as faint edges.
            path_edges = {(u, v) for path in paths for u, v in zip(path, path[1:])}
            for u, v in sorted(path_edges):
                e = g.edge(u, v)
                f = used.get((u, v), {})
                edges.append({"parent": u, "child": v, "position": p["id"],
                              "impact_usd": f.get("impact_usd", 0) if attacked else 0,
                              "remaining_impact_usd": f.get("impact_usd", 0) * (1 - fractions.get(p["id"], 0)),
                              "active": bool(f) and attacked, "collapsed": False,
                              "exposure_pct": e.exposure_pct, "type": e.dep_type,
                              "source": e.source, "note": e.note,
                              "rule": f.get("rule", "inactive alternate channel"),
                              "coefficient": f.get("coefficient")})
    existing = {n["id"] for n in nodes}
    intermediates = sorted({n for e in edges if not e["collapsed"] for n in (e["parent"], e["child"])} - existing)
    for nid in intermediates:
        n = all_nodes[nid]
        column = 2 if n.kind == "lending_market" else 1
        nodes.append({"id": nid, "label": n.label, "kind": n.kind, "column": column,
                      "meta": n.meta, "source": n.meta.get("source")})
    # Aggregate view edges only; allocation and financial evidence stay per position.
    merged = {}
    for e in edges:
        key = (e["parent"], e["child"], e["collapsed"])
        m = merged.setdefault(key, {**e, "impact_usd": 0, "remaining_impact_usd": 0, "evidence": []})
        m["impact_usd"] += e["impact_usd"]
        m["remaining_impact_usd"] += e.get("remaining_impact_usd", 0)
        m["active"] = m["active"] or e["active"]
        m["evidence"].append(e)
    return {"nodes": nodes, "edges": list(merged.values()), "selected": selected,
            "revealed": revealed, "attacked": attacked}
