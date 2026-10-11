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
from blast_radius.fire_drill.challenge import MAX_POSITION_USD, STEP_USD, resize_positions
from blast_radius.fire_drill.catalog import execution_for, load_catalog
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
def prepared(sizes_json: str = ""):
    return prepare(resize_positions(load_catalog(), json.loads(sizes_json)) if sizes_json else load_book()["positions"])


@st.cache_data
def inputs(sizes_json: str = ""):
    book = prepared(sizes_json)
    bundle = execution_for(book.positions)
    return discover(book), exit_options(book, bundle), source_manifest(), bundle


defaults = dict(revealed=False, attacked=False, dependency="issuer:lido", severity=1.0,
                loss_limit=500000.0, locks=[], plan=None, baseline=None, evidence=False,
                before_after="after", last_event=None, portfolio_sizes=None, portfolio_error=None)
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v
state = st.session_state
supported = load_catalog()
original = load_book()["positions"]
sizes_json = json.dumps(state.portfolio_sizes, sort_keys=True) if state.portfolio_sizes else ""
book = prepared(sizes_json)
ranking, execution, manifest, bundle = inputs(sizes_json)
shared = [r for r in ranking if r["positions"] > 1 and r["kind"] != "chain"]
if state.dependency not in {r["id"] for r in ranking}:
    state.dependency = (shared or ranking)[0]["id"]
stress = stress_book(book, state.dependency, state.severity)
selected = next(r for r in ranking if r["id"] == state.dependency)
opaque = [p["id"] for p in book.positions if any(n.meta.get("unmapped") for n in book.graphs[p["id"]].nodes())]
revision = f"{state.dependency}:{state.severity}:{','.join(state.locks)}:{state.loss_limit}"
scenario_revision = f"{state.dependency}:{state.severity}:{sizes_json}"
if sizes_json:
    revision += ":" + sizes_json


def apply_portfolio(sizes):
    try:
        positions = resize_positions(supported, sizes)
    except ValueError as error:
        state.portfolio_error = str(error)
        return
    state.portfolio_sizes = None if positions == original else sizes
    state.portfolio_error = None
    state.revealed = state.attacked = state.evidence = False
    state.plan = state.baseline = None
    state.locks = [pid for pid in state.locks if pid in {p["id"] for p in positions}]
    state.before_after = "after"


payload = {
    "ranking": ranking, "shared": shared, "selected": selected,
    "stress": stress, "execution_summary": {"available_options": sum(len(v)-1 for v in execution["options"].values()),
                                             "unavailable_options": len(execution["unavailable"])},
    "network": network(book, ranking, stress, state.revealed, state.attacked,
                       state.plan if state.before_after == "after" else None),
    "state": {k: state[k] for k in defaults if k != "last_event"}, "revision": revision,
    "scenario_revision": scenario_revision,
    "ack": state.last_event,
    "snapshot": bundle.get("captured_at", "missing quote bundle"),
    "snapshot_window": manifest["presentation_evidence_window_utc"],
    "bundle_hash": manifest["bundle_sha256"], "assumptions": ASSUMPTIONS,
    "coefficients": {**PASS_THROUGH, "pt_underlying_claim_override": 1.0}, "opaque_positions": opaque,
    "positions": book.positions,
    "challenge": {"supported": supported, "step_usd": STEP_USD, "max_usd": MAX_POSITION_USD},
    "sources": [{k: r[k] for k in ("path", "source", "cached_at", "label", "sha256")}
                for r in manifest["sources"] if "morpho" in (r.get("label") or "") or
                "fire_drill" in (r.get("label") or "")],
    "quote_bundle": bundle,
}

fallback = st.query_params.get("fallback") == "1"
if fallback:
    st.title("Blast Radius — Break My Portfolio")
    st.caption("Native controls · frozen evidence · same Python stress and optimization engines")
    with st.expander("Challenge this portfolio"):
        st.caption("Select admitted Ethereum instruments. Zero removes a position. Pendle exits use exact captured 50k–1M USD trades; larger holdings can remain partly unprotected. Morpho uses frozen funded claims and shared liquidity.")
        selected_ids = st.multiselect("Portfolio instruments (maximum ten)", [p["id"] for p in supported],
                         default=[p["id"] for p in book.positions], key="catalog_selection_" + sizes_json,
                         format_func=lambda pid: next(p["label"] for p in supported if p["id"] == pid))
        with st.form("portfolio_challenge"):
            sizes = {p["id"]: st.number_input(p["label"], min_value=0, max_value=MAX_POSITION_USD,
                     step=STEP_USD, value=int((state.portfolio_sizes or {}).get(p["id"], p["size_usd"]) or 500_000),
                     key="allocation_" + p["id"] + sizes_json) if p["id"] in selected_ids else 0 for p in supported}
            if st.form_submit_button("Apply portfolio & rediscover"):
                apply_portfolio(sizes)
                st.rerun()
        if state.portfolio_error:
            st.error(state.portfolio_error)
        if st.button("Restore original portfolio"):
            for k, v in defaults.items():
                if k != "last_event":
                    state[k] = v
            st.rerun()
    if st.button("Find My Weakest Point"):
        state.revealed = True
        state.dependency = (shared or ranking)[0]["id"]
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
        state.loss_limit, state.locks, state.plan, state.baseline = limit, locks, None, None
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
                if k != "last_event":
                    state[k] = v
        elif kind == "discover":
            state.revealed, state.dependency = True, (shared or ranking)[0]["id"]
            state.plan, state.baseline = None, None
        elif kind == "portfolio" and event.get("revision") == revision:
            apply_portfolio(event.get("sizes"))
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
        elif kind == "constraints" and event.get("revision") == revision:
            state.loss_limit = max(0, float(event["limit"]))
            state.locks = sorted(set(event.get("locks", [])) & {p["id"] for p in book.positions})
            state.plan, state.baseline = None, None
            state.evidence = False
            state.before_after = "before"
        elif kind == "rescue" and event.get("scenario_revision") == scenario_revision:
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
    st.caption(f"Illustrative ${stress['aum_usd']:,.0f} allocation across {len(book.positions)} real instruments. Composite captures: "
               + " to ".join(manifest["presentation_evidence_window_utc"])
               + ". Retrieval times and provider mark times differ; manual mappings are versioned files.")
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
                        st.json([{**vars(g.edge(u, v)), "coefficient_assumption":
                                  (1.0 if g.edge(u,v).dep_type == "backing" and
                                   (g.node(u).meta.get("pt") or g.node(u).meta.get("is_pendle_pt"))
                                   else PASS_THROUGH.get(g.edge(u,v).dep_type)),
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
        st.json({**PASS_THROUGH, "pt_underlying_claim_override": 1.0})
    st.download_button("Download decision receipt", json.dumps(receipt(stress, execution, state.plan, manifest, bundle,
                                                                     positions=book.positions, catalog_mode=True), indent=2),
                       file_name="blast-radius-decision.json", mime="application/json")

with st.sidebar:
    st.caption("RESEARCH & REPRODUCTION")
    st.write("The presentation runs from frozen evidence. Research pages preserve the original expected-loss analysis.")
    st.link_button("Native-control fallback", "/?fallback=1")
    st.caption("Run: .venv/Scripts/python.exe -m streamlit run app/Home.py")
