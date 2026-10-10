"""Plotly dependency-graph rendering, shared by all tabs.

Left-to-right layered layout (x = distance from the position) so the dependency *layers*
read clearly. Node colour = share of expected loss (red = dominant risk); manual/reconstructed
edges are dashed so judges can see exactly which facts are not live-fetched.
"""
from __future__ import annotations

import networkx as nx
import plotly.graph_objects as go

from blast_radius.discovery.graph import DependencyGraph

KIND_SYMBOL = {
    "position": "star", "chain": "square", "token": "circle", "oracle": "diamond",
    "amm": "triangle-up", "lending_market": "square-dot", "issuer": "hexagon",
    "custodian": "x",
}
KIND_LABEL = {
    "position": "Position", "chain": "Settlement chain", "token": "Asset / backing",
    "oracle": "Oracle", "amm": "AMM / liquidity", "lending_market": "Lending market",
    "issuer": "Issuer", "custodian": "Custodian",
}


def _layered_positions(g: DependencyGraph) -> dict:
    lengths = nx.single_source_shortest_path_length(g.g, g.root_id)
    layers: dict[int, list] = {}
    for n in g.g.nodes:
        layers.setdefault(lengths.get(n, 0), []).append(n)
    pos = {}
    for layer, nodes in layers.items():
        nodes = sorted(nodes, key=lambda n: g.node(n).label.lower())
        k = len(nodes)
        for i, n in enumerate(nodes):
            pos[n] = (layer, (i - (k - 1) / 2.0))
    return pos, max((len(v) for v in layers.values()), default=1)


def build_figure(g: DependencyGraph, node_shares: dict | None = None,
                 highlight: set | None = None, title: str = "") -> go.Figure:
    node_shares = node_shares or {}
    highlight = highlight or set()
    pos, max_layer = _layered_positions(g)

    # --- edges (solid = live API, dashed = manual/reconstructed) ---
    edge_traces = []
    for manual, dash, color in [(False, "solid", "rgba(130,140,160,0.55)"),
                                (True, "dash", "rgba(220,130,60,0.75)")]:
        ex, ey = [], []
        for e in g.edges():
            if e.is_manual != manual:
                continue
            x0, y0 = pos[e.parent]
            x1, y1 = pos[e.child]
            ex += [x0, x1, None]
            ey += [y0, y1, None]
        edge_traces.append(go.Scatter(
            x=ex, y=ey, mode="lines", line=dict(width=1.1, color=color, dash=dash),
            hoverinfo="none", name="manual edge" if manual else "live-API edge",
            showlegend=True))

    # --- nodes ---
    nx_, ny_, text, hover, color, size, symbol, line_w, line_c = ([] for _ in range(9))
    for n in g.g.nodes:
        node = g.node(n)
        x, y = pos[n]
        share = node_shares.get(n, 0.0)
        nx_.append(x); ny_.append(y)
        text.append(node.label)
        meta = node.meta
        hv = [f"<b>{node.label}</b>", f"type: {KIND_LABEL.get(node.kind, node.kind)}"]
        if meta.get("risk_category"):
            hv.append(f"risk: {meta['risk_category']}")
        if share:
            hv.append(f"share of expected loss: {share*100:.1f}%")
        if meta.get("lltv"):
            try:
                hv.append(f"LLTV: {int(meta['lltv'])/1e18:.0%}")
            except Exception:
                pass
        if meta.get("utilization") is not None:
            hv.append(f"utilization: {meta['utilization']*100:.0f}%")
        if meta.get("liquidity_usd"):
            hv.append(f"liquidity: ${meta['liquidity_usd']:,.0f}")
        if meta.get("source"):
            hv.append(f"source: {meta['source']}")
        if meta.get("unmapped"):
            hv.append("⚠ backing not mapped (opaque)")
        hover.append("<br>".join(hv))
        color.append(share)
        size.append(16 + 46 * min(share, 0.6) + (10 if node.kind == "position" else 0))
        symbol.append(KIND_SYMBOL.get(node.kind, "circle"))
        line_w.append(3 if n in highlight else 1)
        line_c.append("#f1c40f" if n in highlight else "rgba(20,24,34,0.8)")

    node_trace = go.Scatter(
        x=nx_, y=ny_, mode="markers+text", text=text, textposition="top center",
        textfont=dict(size=10), hovertext=hover, hoverinfo="text",
        marker=dict(size=size, symbol=symbol, color=color, colorscale="YlOrRd", cmin=0.0,
                    cmax=max(0.15, max(color) if color else 0.15),
                    line=dict(width=line_w, color=line_c),
                    colorbar=dict(title="share of<br>exp. loss", thickness=12, len=0.5)),
        showlegend=False)

    fig = go.Figure(edge_traces + [node_trace])
    fig.update_layout(
        title=title, height=max(460, max_layer * 46 + 160),
        margin=dict(l=10, r=10, t=40 if title else 10, b=10),
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
        hoverlabel=dict(bgcolor="white", font_size=12))
    return fig
