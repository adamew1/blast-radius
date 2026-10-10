"""Blast Radius — an evidence-backed portfolio fire drill."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["BLAST_RADIUS_OFFLINE"] = "1"

import streamlit as st

from app.components.terminal import render_terminal
from blast_radius.fire_drill.evidence import ASSUMPTIONS, receipt, source_manifest
from blast_radius.fire_drill.execution import exit_options, load_execution
from blast_radius.fire_drill.model import discover, prepare, stress_book
from blast_radius.fire_drill.optimize import plan_rescue
from blast_radius.fire_drill.presentation import network
from blast_radius.models.passthrough import PASS_THROUGH
from blast_radius.portfolio.book import load_book

st.set_page_config(page_title="Blast Radius · Portfolio Fire Drill", page_icon="◈", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown("""<style>
[data-testid=stAppViewContainer]{background:#080d16;color:#e7edf5}
[data-testid=stHeader]{background:transparent;height:2.5rem}
.block-container{padding:2.2rem 1.8rem 2rem;max-width:1800px}
[data-testid=stSidebar]{background:#101925}
[data-testid=stMain] a{color:#50d9c4}
[data-testid=stMain] h1,[data-testid=stMain] h2,[data-testid=stMain] h3{color:#e7edf5}
[data-testid=stMain] [data-testid=stCaptionContainer]{color:#8fa3ba}
[data-testid=stMain] button{border-radius:8px}
@media(max-width:800px){.block-container{padding:2rem .5rem}}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def prepared():
    return prepare(load_book()["positions"])


@st.cache_data
def inputs():
    book = prepared()
    bundle = load_execution()
    return discover(book), exit_options(book, bundle), source_manifest(), bundle


book = prepared()
ranking, execution, manifest, bundle = inputs()
defaults = dict(revealed=False, attacked=False, dependency="issuer:lido", severity=1.0,
                loss_limit=500000.0, locks=[], plan=None, baseline=None, evidence=False,
                before_after="after", last_event=None)
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v
state = st.session_state
stress = stress_book(book, state.dependency, state.severity)
selected = next(r for r in ranking if r["id"] == state.dependency)
shared = [r for r in ranking if r["positions"] > 1 and r["kind"] != "chain"]
opaque = [p["id"] for p in book.positions if any(n.meta.get("unmapped") for n in book.graphs[p["id"]].nodes())]
revision = f"{state.dependency}:{state.severity}:{','.join(state.locks)}:{state.loss_limit}"
payload = {
    "ranking": ranking, "shared": shared, "selected": selected,
    "stress": stress, "execution_summary": {"available_options": sum(len(v)-1 for v in execution["options"].values()),
                                             "unavailable_options": len(execution["unavailable"])},
    "network": network(book, ranking, stress, state.revealed, state.attacked,
                       state.plan if state.before_after == "after" else None),
    "state": {k: state[k] for k in defaults if k != "last_event"}, "revision": revision,
    "ack": state.last_event,
    "snapshot": bundle.get("captured_at", "missing quote bundle"),
    "bundle_hash": manifest["bundle_sha256"], "assumptions": ASSUMPTIONS,
    "coefficients": PASS_THROUGH, "opaque_positions": opaque,
    "positions": book.positions,
    "sources": [{k: r[k] for k in ("path", "source", "cached_at", "label", "sha256")}
                for r in manifest["sources"] if "morpho" in (r.get("label") or "") or
                "fire_drill" in (r.get("label") or "")],
    "quote_bundle": bundle,
}

fallback = st.query_params.get("fallback") == "1"
if fallback:
    st.title("Blast Radius — Break My Portfolio")
    st.caption("Native controls · frozen evidence · same Python stress and optimization engines")
    if st.button("Find My Weakest Point"):
        state.revealed = True
        state.dependency = shared[0]["id"]
        state.plan = None
        st.rerun()
    options = [r["id"] for r in ranking]
    dep = st.selectbox("Dependency", options, index=options.index(state.dependency),
                       format_func=lambda nid: next(r["label"] for r in ranking if r["id"] == nid))
    severity = st.slider("Failure severity", 0, 100, int(state.severity * 100))
    if dep != state.dependency or severity / 100 != state.severity:
        state.dependency, state.severity, state.plan = dep, severity / 100, None
        state.attacked = state.revealed = True
        st.rerun()
    c = st.columns(3)
    c[0].metric("Portfolio", f"${stress['aum_usd']:,.0f}")
    c[1].metric("Scenario loss", f"${stress['loss_usd']:,.0f}")
    c[2].metric("Positions exposed", stress["exposed_positions"])
    import plotly.graph_objects as go
    graph = payload["network"]
    layout = {n["id"]: (n["column"], n.get("row", i)) for i, n in enumerate(graph["nodes"])}
    fig = go.Figure()
    for e in graph["edges"]:
        a, b = layout[e["parent"]], layout[e["child"]]
        fig.add_trace(go.Scatter(x=[a[0], b[0]], y=[a[1], b[1]], mode="lines",
                                 line={"color": "#ef6574" if e["active"] else "#33455c"}, showlegend=False))
    fig.add_trace(go.Scatter(x=[layout[n["id"]][0] for n in graph["nodes"]],
                             y=[layout[n["id"]][1] for n in graph["nodes"]], mode="markers+text",
                             text=[n["label"] for n in graph["nodes"]], textposition="top center"))
    fig.update_layout(template="plotly_dark", height=600, showlegend=False)
    st.plotly_chart(fig, width="stretch")
    limit = st.number_input("Maximum accounted scenario loss", min_value=0.0, value=float(state.loss_limit))
    locks = st.multiselect("Lock positions", [p["id"] for p in book.positions], default=state.locks)
    if limit != state.loss_limit or locks != state.locks:
        state.loss_limit, state.locks, state.plan = limit, locks, None
    if st.button("BUILD RESCUE PLAN"):
        state.plan = plan_rescue(stress, execution, state.loss_limit, state.locks)
    if state.plan:
        st.json(state.plan)
    state.evidence = st.checkbox("Show Me the Evidence", value=state.evidence)
else:
    result = render_terminal(payload)
    event = result.action
    if event and event.get("nonce") != state.last_event:
        state.last_event = event.get("nonce")
        kind = event.get("type")
        if kind == "reset":
            for k, v in defaults.items():
                state[k] = v
        elif kind == "discover":
            state.revealed, state.dependency = True, shared[0]["id"]
            state.plan, state.baseline = None, None
        elif kind == "select" and event.get("id") in {r["id"] for r in ranking}:
            state.dependency = event["id"]
            state.revealed = True
            state.plan, state.baseline = None, None
        elif kind == "severity":
            state.severity = max(0, min(1, float(event["value"])))
            state.plan, state.baseline = None, None
        elif kind == "attack":
            state.revealed = state.attacked = True
            state.plan, state.baseline = None, None
        elif kind == "rescue" and event.get("revision") == revision:
            state.loss_limit = max(0, float(event["limit"]))
            state.locks = sorted(set(event.get("locks", [])) & {p["id"] for p in book.positions})
            state.attacked = state.revealed = True
            state.plan = plan_rescue(stress, execution, state.loss_limit, state.locks)
            state.baseline = plan_rescue(stress, execution, state.loss_limit, state.locks, mode="exit_affected")
            state.before_after = "after"
        elif kind == "view":
            state.before_after = "before" if event.get("value") == "before" else "after"
        elif kind == "evidence":
            state.evidence = not state.evidence
        st.rerun()

if state.evidence:
    st.subheader("Show Me the Evidence")
    st.caption("Frozen API observations + sourced manual mappings + cached RPC decimals. No live-data claim.")
    a, b, c = st.tabs(["Dependencies & coefficients", "Quotes & liquidity", "Model & receipt"])
    with a:
        st.write("Selected dependency", selected)
        for p in book.positions:
            g = book.graphs[p["id"]]
            if g.has_node(state.dependency):
                with st.expander(p["label"]):
                    import networkx as nx
                    paths = list(nx.all_simple_paths(g.g, g.root_id, state.dependency))
                    for path in paths:
                        st.write(" → ".join(g.node(n).label for n in path))
                        st.json([{**vars(g.edge(u, v)), "coefficient_assumption": PASS_THROUGH.get(g.edge(u,v).dep_type),
                                  "child_metadata": g.node(v).meta} for u, v in zip(path, path[1:])])
        st.json(manifest)
    with b:
        st.caption("Pendle: value quoted output once; reported fees are already included. RPC-verified decimals. "
                   "Morpho: funded allocation and shared-market bounds, not withdrawal-queue certification.")
        st.json(bundle)
        st.json(execution)
        if state.plan:
            st.json(state.plan.get("audit", {}))
    with c:
        for assumption in ASSUMPTIONS:
            st.write("• " + assumption)
        st.json(PASS_THROUGH)
    st.download_button("Download decision receipt", json.dumps(receipt(stress, execution, state.plan, manifest, bundle), indent=2),
                       file_name="blast-radius-decision.json", mime="application/json")

with st.sidebar:
    st.caption("RESEARCH & REPRODUCTION")
    st.write("The presentation runs from frozen evidence. Research pages preserve the original expected-loss analysis.")
    st.link_button("Native-control fallback", "/?fallback=1")
    st.caption("Run: .venv/Scripts/python.exe -m streamlit run app/Home.py")
