"""Native live workflow; snapshot presentation stays independent and offline."""
from __future__ import annotations

import json
import time

import streamlit as st

from blast_radius.fire_drill.catalog import load_catalog
from blast_radius.fire_drill.challenge import resize_positions
from blast_radius.fire_drill.live import (LIVE_ASSUMPTIONS, analyze_live, capture_live,
                                          live_receipt, save_live_receipt)
from blast_radius.fire_drill.model import discover
from blast_radius.fire_drill.presentation import network
from blast_radius.portfolio.book import load_book
from blast_radius.sources.live import LiveInputError


def snapshot_fallback():
    st.session_state.data_mode = "Snapshot Mode"


def clear_live_analysis():
    st.session_state.pop("live_analysis", None)


def graph_dot(view):
    lines = ['digraph { rankdir=LR; bgcolor="#080d16"; node [style=filled fillcolor="#152335" fontcolor="white" color="#33455c"];']
    for n in view["nodes"]:
        lines.append(f'{json.dumps(n["id"])} [label={json.dumps(n["label"])}];')
    for e in view["edges"]:
        color = "#ef6574" if e["active"] else "#526780"
        lines.append(f'{json.dumps(e["parent"])} -> {json.dumps(e["child"])} [color="{color}"];')
    return "\n".join(lines + ["}"])


@st.fragment(run_every="15s")
def render_live():
    st.title("Blast Radius · Live Mode")
    st.caption("Discover → Attack → Collapse → Rescue → Prove · supported Ethereum catalog · hypothetical allocations")
    st.info("Fresh protocol observations with versioned manual dependencies and assumed costs. "
            "Model rescues are indicative: cash conversion and Morpho withdrawal execution are not certified.")
    catalog = load_catalog()
    default_sizes = {p["id"]: p["size_usd"] for p in load_book()["positions"]}
    with st.expander("Choose supported instruments and quote sizes"):
        ids = st.multiselect("Live portfolio instruments (up to ten)", [p["id"] for p in catalog],
                             default=list(default_sizes), key="live_selected",
                             format_func=lambda pid: next(p["label"] for p in catalog if p["id"] == pid))
        sizes = {p["id"]: st.number_input(p["label"], min_value=50_000, max_value=2_000_000,
                                         value=default_sizes.get(p["id"], 500_000), step=50_000,
                                         key="live_size_" + p["id"]) if p["id"] in ids else 0 for p in catalog}
        grid = st.selectbox("Requested quote grid", ["25% steps (four per PT)", "5% steps (twenty per PT)", "Risk only (no quotes)"], key="live_grid")
        st.caption("Each candidate needs its own exact integer-token quote. Missing sizes are excluded. "
                   "Rate limits can leave fewer candidates. Discovery of PT lending contagion covers the eight admitted vaults.")
    try:
        positions = resize_positions(catalog, sizes)
    except ValueError as exc:
        st.error(str(exc))
        return
    steps = list(range(1, 21)) if grid.startswith("5%") else [] if grid.startswith("Risk") else [5, 10, 15, 20]
    run = st.session_state.get("live_run")
    changed = run and (run.positions != positions or run.quote_steps != steps)
    if changed:
        st.warning("Portfolio or quote grid changed. Refresh before analysis.")
        clear_live_analysis()
    if st.button("Fetch fresh data & discover", type="primary", key="live_refresh"):
        # A failed refresh must not leave an earlier successful analysis on screen.
        st.session_state.pop("live_run", None)
        clear_live_analysis()
        with st.spinner("Retrieving timestamped Morpho/Pendle observations and exact-size quotes…"):
            run = capture_live(positions, quote_steps=steps)
        st.session_state.live_run = run
        save_live_receipt(live_receipt(run))
        changed = False
    if run is None:
        st.caption("No live observations yet. Fetch data to start. Snapshot Mode is available above.")
        return
    status = run.freshness()
    st.write("Freshness:", status["status"])
    st.caption("As-of provider state window (UTC): " + " → ".join(status["as_of_window_utc"])
               + " · retrieved through " + time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(run.completed_at)))
    with st.expander("Sources, timestamps and freshness checks"):
        st.json(status)
        st.dataframe([{"source": o["request"]["url"], "method": o["request"]["method"],
                       "received_at": o["received_at"], "observation": o["key"],
                       "error": o.get("error", "")} for o in run.client.observations], width="stretch")
    analysis = None
    if changed or not status["risk_usable"]:
        clear_live_analysis()
        st.error("Live analysis rejected. " + (status["risk_error"] or "Inputs expired or changed; fetch a new run."))
    else:
        ranking = discover(run.book)
        shared = [r for r in ranking if r["positions"] > 1 and r["kind"] != "chain"]
        choices = {r["id"]: r for r in ranking}
        if st.session_state.get("live_dependency") not in choices:
            st.session_state.live_dependency = (shared or ranking)[0]["id"]
        st.write("Discovered shared dependencies")
        st.dataframe(shared or ranking, width="stretch", hide_index=True)
        dependency = st.selectbox("Attack dependency", list(choices), key="live_dependency",
                                  format_func=lambda nid: choices[nid]["label"], on_change=clear_live_analysis)
        severity = st.slider("Intrinsic shock (%)", 0, 100, 100, key="live_severity", on_change=clear_live_analysis) / 100
        try:
            analysis = analyze_live(run, dependency, severity)
        except LiveInputError as exc:
            # The observations can expire during discovery or a timer render.
            clear_live_analysis()
            st.error(str(exc))
            return
        stress = analysis["scenario"]
        cols = st.columns(3)
        cols[0].metric("Portfolio", f"${stress['aum_usd']:,.0f}")
        cols[1].metric("Conditional scenario loss", f"${stress['loss_usd']:,.2f}")
        cols[2].metric("Exposed positions", stress["exposed_positions"])
        st.dataframe([{k: p[k] for k in ("label", "size_usd", "loss_usd", "fraction", "apy")}
                      for p in stress["positions"]], width="stretch", hide_index=True)
        with st.expander("Collapse paths and rebuilt dependency graph"):
            view = network(run.book, ranking, stress, True, True)
            st.graphviz_chart(graph_dot(view))
            st.json(view)
        limit = st.number_input("Maximum accounted scenario loss (USD)", min_value=0.0, value=500_000.0,
                                step=50_000.0, key="live_limit", on_change=clear_live_analysis)
        valid_ids = {p["id"] for p in positions}
        st.session_state.live_locks = [pid for pid in st.session_state.get("live_locks", []) if pid in valid_ids]
        locks = st.multiselect("Lock positions", [p["id"] for p in positions], key="live_locks", on_change=clear_live_analysis)
        if not status["execution_usable"]:
            clear_live_analysis()
            st.warning("Risk-only analysis. No executable rescue plan or indicative optimization is available: "
                       + "; ".join(status["execution_errors"] + [r["reason"] for r in status["rejections"]]))
        if st.button("Calculate indicative model rescue", disabled=not status["execution_usable"], key="live_rescue"):
            try:
                analysis = analyze_live(run, dependency, severity, loss_limit=limit, locks=locks, rescue=True)
                # Recheck after solver work; never display an expired plan.
                if not run.freshness()["execution_usable"]:
                    raise LiveInputError("Execution observations expired while solving; refresh the run")
                st.session_state.live_analysis = analysis
                save_live_receipt(live_receipt(run, analysis))
            except LiveInputError as exc:
                clear_live_analysis()
                st.error(str(exc))
        if st.session_state.get("live_analysis") and status["execution_usable"]:
            analysis = st.session_state.live_analysis
            st.warning("Indicative model rescue · not executable · assumed gas and cash conversion · no guaranteed fill")
            st.json(analysis["plan"])
    with st.expander("Prove: observations, manual mappings and assumptions"):
        for assumption in LIVE_ASSUMPTIONS:
            st.write("• " + assumption)
        st.json(run.mappings)
        st.json(run.bundle)
    rec = live_receipt(run, analysis)
    # Timer reruns recheck freshness, but only new decisions create new files.
    decision = (run.completed_at, None if analysis is None else
                (analysis["scenario"], analysis["exit_candidates"], analysis["plan"]))
    if st.session_state.get("live_receipt_decision") != decision:
        st.session_state.live_receipt_decision = decision
        st.session_state.live_download_receipt = rec
        st.session_state.live_receipt_path = save_live_receipt(rec)
    rec = st.session_state.live_download_receipt
    path = st.session_state.live_receipt_path
    st.caption("Reproducible receipt saved to " + str(path.relative_to(path.parents[2]))
               + ". Replay checks freshness at the historical run time; replay does not make evidence fresh now.")
    st.download_button("Download live observation receipt", json.dumps(rec, indent=2, allow_nan=False),
                       file_name="blast-radius-live-receipt.json", mime="application/json", key="live_download")
