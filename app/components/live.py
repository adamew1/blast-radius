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
from blast_radius.sources.live import FreshnessPolicy, LiveInputError, ObservationClient, digest, timestamp, utc


def snapshot_fallback():
    st.session_state.data_mode = "Snapshot Mode"


def clear_live_analysis():
    st.session_state.pop("live_analysis", None)


def load_hakutora_example():
    """Explicitly replace the Live portfolio; never substitute on a failed fetch."""
    for key in ("live_run", "live_analysis", "live_receipt_decision", "live_download_receipt", "live_receipt_path"):
        st.session_state.pop(key, None)
    st.session_state.live_selected = ["hakutora-usdc"]
    st.session_state["live_size_hakutora-usdc"] = 1_000_000
    st.session_state.live_grid = "25% steps (four per PT)"
    st.session_state.live_risk_age_minutes = 15
    st.session_state.live_dependency = "token:ethereum:0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf"
    st.session_state.live_severity = 100
    st.session_state.live_limit = 500_000.0
    st.session_state.live_locks = []


def risk_data_status(status):
    """Distinguish the selected acceptance window from the strict live standard."""
    checks = [c for c in status["checks"] if c["kind"] == "risk"]
    max_age = max((c["age_seconds"] for c in checks), default=0)
    times = [c["observed_at"] for c in checks]
    skew = max(times) - min(times) if times else 0
    strict = FreshnessPolicy()
    delayed = max_age > strict.risk_seconds or skew > strict.max_skew_seconds
    return {"classification": "rejected" if not status["risk_usable"] else
            "delayed risk observations" if delayed else "fresh risk observations",
            "strict_15_minute_risk_passed": bool(status["risk_usable"] and not delayed),
            "maximum_observed_risk_age_seconds": max_age, "risk_timestamp_spread_seconds": skew,
            "selected_risk_age_limit_seconds": status["policy"]["risk_seconds"],
            "selected_risk_spread_limit_seconds": status["policy"]["max_skew_seconds"]}


def observation_receipt(run, analysis=None):
    rec = live_receipt(run, analysis)
    status = analysis["freshness"] if analysis else rec["freshness_at_capture"]
    rec["risk_data_status"] = risk_data_status(status)
    if rec["risk_data_status"]["classification"] == "delayed risk observations":
        rec["classification"] = "delayed protocol observations; indicative analysis, not verified fresh live data"
    elif not status["risk_usable"]:
        rec["classification"] = "rejected protocol observations; no verified current analysis"
    rec.pop("receipt_sha256")
    rec["receipt_sha256"] = digest(rec)
    return rec


def rejected_morpho_inputs(run, status):
    """Describe rejected identities from the captured data, without accepting them."""
    reasons = " ".join([status["risk_error"] or ""] +
                       [r["reason"] for r in status["rejections"] if r["kind"] == "risk"]).lower()
    selected = {p["id"] for p in run.positions}
    rows = {}
    for p in run.catalog:
        vault = run.vault_records.get(p.get("vault", "").lower())
        if not isinstance(vault, dict) or not isinstance(vault.get("state"), dict):
            continue
        state = vault["state"]
        inputs = [(p["id"], "vault", state)]
        allocations = state.get("allocation")
        for allocation in allocations if isinstance(allocations, list) else []:
            if not isinstance(allocation, dict) or not isinstance(allocation.get("market"), dict):
                continue
            market = allocation["market"]
            mid = market.get("marketId", "")
            if isinstance(mid, str) and mid and allocation.get("supplyAssetsUsd"):
                def symbol(key):
                    asset = market.get(key)
                    return asset.get("symbol", "unknown asset") if isinstance(asset, dict) else "unknown asset"
                market_state = market.get("state")
                inputs.append((mid, f"{symbol('collateralAsset')} / {symbol('loanAsset')} market",
                               market_state if isinstance(market_state, dict) else {}))
        for identity, label, observation in inputs:
            if identity.lower() not in reasons:
                continue
            row = rows.setdefault(identity, {"identity": identity, "input": label, "positions": [],
                                             "scope": [], "provider_time_utc": "Unavailable",
                                             "age_seconds": None, "max_age_seconds": run.client.policy.risk_seconds})
            row["positions"].append(p["label"])
            row["scope"].append("selected holding" if p["id"] in selected else "PT contagion discovery")
            try:
                observed = timestamp(observation.get("timestamp"))
                row["provider_time_utc"] = utc(observed)
                row["age_seconds"] = timestamp(status["checked_at"]) - observed
            except (LiveInputError, OverflowError, OSError):
                pass
    return list(rows.values())


def render_rejection(run, status):
    rows = rejected_morpho_inputs(run, status)
    if not rows:
        st.error("Live analysis rejected. " + (status["risk_error"] or "Inputs expired or changed; fetch a new run."))
        return
    for row in rows:
        age = row["age_seconds"]
        timing = (f"{age / 60:.1f} minutes old" if age is not None and age >= 0 else
                  f"{-age / 60:.1f} minutes in the future" if age is not None else "missing a valid timestamp")
        limit = (f"future tolerance {run.client.policy.future_tolerance_seconds} seconds" if age is not None and age < 0
                 else f"maximum age {row['max_age_seconds'] / 60:g} minutes")
        st.error(f"Live analysis rejected. {', '.join(row['positions'])}: {row['input']} is {timing} "
                 f"({limit}). "
                 f"Provider timestamp: {row['provider_time_utc']}.")
    st.info("Morpho returned an observation outside the freshness policy. No current scenario or rescue is available "
            "for this portfolio. Retry after the provider updates, change the selected instruments, "
            "or use ‘Load $1M Hakutora live example’ above and fetch again. "
            "The example must also pass fresh API checks. ‘Use offline Snapshot Mode’ is available above.")
    with st.expander("Rejected input evidence and technical details"):
        st.dataframe(rows, width="stretch", hide_index=True)
        st.write(status["risk_error"] or status["rejections"])


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
    st.info("Timestamped protocol observations with versioned manual dependencies and assumed costs. "
            "Model rescues are indicative: cash conversion and Morpho withdrawal execution are not certified. "
            "Full-book and Pendle live coverage has not passed certification.")
    catalog = load_catalog()
    default_sizes = {p["id"]: p["size_usd"] for p in load_book()["positions"]}
    st.button("Load $1M Hakutora live example", on_click=load_hakutora_example, key="live_example",
              help="Replaces only the Live portfolio with one illustrative $1M Hakutora USDC holding, "
                   "100% cbBTC shock, $500k mandate and strict 15-minute risk policy. Click Fetch to obtain new observations.")
    risk_minutes = st.selectbox("Maximum risk-data age (minutes)", [15, 60], index=1,
                                key="live_risk_age_minutes", on_change=clear_live_analysis)
    policy = FreshnessPolicy(risk_seconds=risk_minutes * 60, max_skew_seconds=risk_minutes * 60)
    if risk_minutes > 15:
        st.warning("60-minute risk-data window selected. Observations older than 15 minutes are labelled delayed; "
                   "this does not certify a fresh live analysis. Risk timestamp spread is also capped at 60 minutes. "
                   "USD marks, exact-size quotes and RPC data still expire after two minutes.")
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
    st.caption(f"Selected live portfolio: {len(positions)} instrument{'s' if len(positions) != 1 else ''} · "
               f"${sum(p['size_usd'] for p in positions):,.0f} illustrative allocation.")
    steps = list(range(1, 21)) if grid.startswith("5%") else [] if grid.startswith("Risk") else [5, 10, 15, 20]
    run = st.session_state.get("live_run")
    changed = run and (run.positions != positions or run.quote_steps != steps or run.client.policy != policy)
    if changed:
        st.warning("Portfolio or quote grid changed. Refresh before analysis." if run.client.policy == policy else
                   "Risk-data age policy changed. Fetch a new run before analysis.")
        clear_live_analysis()
    if st.button("Fetch fresh data & discover", type="primary", key="live_refresh"):
        # A failed refresh must not leave an earlier successful analysis on screen.
        st.session_state.pop("live_run", None)
        clear_live_analysis()
        with st.spinner("Retrieving timestamped Morpho/Pendle observations and exact-size quotes…"):
            run = capture_live(positions, quote_steps=steps, client=ObservationClient(policy=policy))
        st.session_state.live_run = run
        save_live_receipt(observation_receipt(run))
        changed = False
    if run is None:
        st.caption("No live observations yet. Fetch data to start. Snapshot Mode is available above.")
        return
    status = run.freshness()
    risk_status = risk_data_status(status)
    st.write("Freshness:", risk_status["classification"] if risk_status["classification"] == "delayed risk observations"
             else status["status"])
    if risk_status["classification"] == "delayed risk observations":
        st.warning(f"Delayed risk data: oldest validated state is {risk_status['maximum_observed_risk_age_seconds'] / 60:.1f} "
                   "minutes old. Analysis and any indicative rescue use the selected wider policy; "
                   "they have not passed the strict 15-minute live standard.")
    window_label = "As-of provider state window (UTC): " if status["risk_usable"] else \
                   "Validated provider timestamps only (partial; analysis rejected): "
    st.caption(window_label + (" → ".join(status["as_of_window_utc"]) or "none")
               + " · retrieved through " + time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(run.completed_at)))
    with st.expander("Sources, timestamps and freshness checks"):
        st.json(risk_status)
        st.json(status)
        st.dataframe([{"source": o["request"]["url"], "method": o["request"]["method"],
                       "received_at": o["received_at"], "observation": o["key"],
                       "error": o.get("error", "")} for o in run.client.observations], width="stretch")
    analysis = None
    if changed or not status["risk_usable"]:
        clear_live_analysis()
        if changed:
            st.error("Live analysis rejected. Portfolio, quote grid or risk-data policy changed; fetch a new run.")
        else:
            render_rejection(run, status)
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
                save_live_receipt(observation_receipt(run, analysis))
            except LiveInputError as exc:
                clear_live_analysis()
                st.error(str(exc))
        if st.session_state.get("live_analysis") and status["execution_usable"]:
            analysis = st.session_state.live_analysis
            st.warning(("Delayed-data indicative model rescue" if risk_status["classification"] == "delayed risk observations" else
                        "Indicative model rescue") + " · not executable · assumed gas and cash conversion · no guaranteed fill")
            st.json(analysis["plan"])
    with st.expander("Prove: observations, manual mappings and assumptions"):
        for assumption in LIVE_ASSUMPTIONS:
            st.write("• " + assumption)
        st.json(run.mappings)
        st.json(run.bundle)
    rec = observation_receipt(run, analysis)
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
