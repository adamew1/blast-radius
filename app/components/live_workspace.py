"""Live presentation using the same terminal as Snapshot, with honest recovery."""
from __future__ import annotations

import json
import time

import streamlit as st

from app.components import live as ui
from app.components.terminal import render_terminal
from app.live_data import verify_live_receipt
from blast_radius.config import ROOT
from blast_radius.fire_drill.catalog import load_catalog
from blast_radius.fire_drill.challenge import resize_positions
from blast_radius.fire_drill.model import discover
from blast_radius.fire_drill.optimize import plan_rescue
from blast_radius.fire_drill.presentation import network
from blast_radius.portfolio.book import load_book
from blast_radius.sources.live import FreshnessPolicy, LiveInputError, ObservationClient, digest, utc

SAVED_RUN = ROOT / "artifacts/certified_live/hakutora_native_delayed_20261011_receipt.json"


def reset_stages():
    for name, value in {"live_revealed": False, "live_attacked": False, "live_evidence": False,
                        "live_before_after": "before", "live_last_event": None}.items():
        st.session_state[name] = value
    ui.clear_live_analysis()


def start_demo():
    ui.load_hakutora_example()
    st.session_state.live_risk_age_minutes = 60
    reset_stages()
    st.session_state.live_start_requested = True


def replay_saved():
    """Use genuine embedded observations, never fabricate an API response."""
    try:
        rec = json.loads(SAVED_RUN.read_text(encoding="utf-8"))
        run = verify_live_receipt(rec)
        decision = rec["analysis"]["analyzed_at"]
        run.client.clock = lambda: decision
        run.replay_context = {"mode": "historical replay", "source_receipt_sha256": rec["receipt_sha256"],
                              "recorded_decision_utc": utc(decision), "fresh_at_replay": False}
        ui.load_hakutora_example()
        st.session_state.live_risk_age_minutes = rec["policy"]["risk_seconds"] // 60
        st.session_state.live_run = run
        reset_stages()
        st.session_state.live_replay = True
        st.session_state.live_notice = None
    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.session_state.live_notice = "Saved evidence could not be verified. Use offline Snapshot Mode. " + str(exc)


def revision(run):
    state = st.session_state
    return digest({"capture": run.completed_at, "positions": run.positions,
                   "dependency": state.get("live_dependency"), "severity": state.get("live_severity", 100),
                   "limit": state.get("live_limit", 500_000.0), "locks": state.get("live_locks", []),
                   "mode": "replay" if getattr(run, "replay_context", None) else "live"})


def calculate(run):
    state = st.session_state
    result = ui.analyze_live(run, state.live_dependency, state.live_severity / 100,
                             loss_limit=state.live_limit, locks=state.live_locks, rescue=True)
    baseline = plan_rescue(result["scenario"], result["exit_candidates"], state.live_limit,
                           state.live_locks, mode="exit_affected")
    if not run.freshness()["execution_usable"]:
        raise LiveInputError("Execution observations expired while solving; refresh the run")
    state.live_baseline = baseline
    state.live_analysis = result
    state.live_revealed = state.live_attacked = True
    state.live_before_after = "after"


def apply_action(event):
    state = st.session_state
    run = state.get("live_run")
    if not run or event.get("nonce") == state.get("live_last_event"):
        return
    state.live_last_event = event.get("nonce")
    if event.get("revision") != revision(run):
        state.live_notice = "The inputs changed. Review the current scenario and try again."
        return
    kind = event.get("type")
    try:
        if kind == "reset":
            reset_stages()
            state.live_last_event = event.get("nonce")
        elif kind == "portfolio":
            if getattr(run, "replay_context", None):
                raise LiveInputError("Saved replay keeps its recorded portfolio. Fetch new API data to change holdings.")
            positions = resize_positions(load_catalog(), event.get("sizes"))
            state.live_selected = [p["id"] for p in positions]
            for p in positions:
                state["live_size_" + p["id"]] = int(p["size_usd"])
            state.pop("live_run", None)
            reset_stages()
            state.live_notice = "Portfolio applied. Click Fetch fresh data & discover to analyze these holdings."
        elif kind == "discover":
            state.live_revealed = True
            ui.clear_live_analysis()
        elif kind == "select":
            if event.get("id") not in {r["id"] for r in discover(run.book)}:
                raise LiveInputError("Choose a discovered dependency.")
            state.live_dependency = event["id"]
            state.live_revealed = True
            ui.clear_live_analysis()
        elif kind == "severity":
            state.live_severity = int(round(100 * max(0, min(1, float(event["value"])))))
            ui.clear_live_analysis()
        elif kind == "attack":
            state.live_revealed = state.live_attacked = True
            ui.clear_live_analysis()
        elif kind in ("constraints", "rescue"):
            valid = {p["id"] for p in run.positions}
            state.live_limit = max(0.0, float(event["limit"]))
            state.live_locks = sorted(set(event.get("locks", [])) & valid)
            ui.clear_live_analysis()
            if kind == "rescue":
                calculate(run)
        elif kind == "view":
            state.live_before_after = "before" if event.get("value") == "before" else "after"
        elif kind == "evidence":
            state.live_evidence = not state.get("live_evidence", False)
    except (LiveInputError, ValueError, KeyError, TypeError) as exc:
        ui.clear_live_analysis()
        state.live_notice = str(exc)


def payload(run, analysis, ranking, status):
    state = st.session_state
    stress = analysis["scenario"]
    selected = next(r for r in ranking if r["id"] == state.live_dependency)
    plan = (state.get("live_analysis") or {}).get("plan")
    candidates = analysis.get("exit_candidates") or {"options": {}, "unavailable": []}
    replay = getattr(run, "replay_context", None)
    delayed = ui.risk_data_status(status)["classification"] == "delayed risk observations"
    state_view = {"revealed": state.get("live_revealed", False), "attacked": state.get("live_attacked", False),
                  "evidence": state.get("live_evidence", False), "plan": plan,
                  "baseline": state.get("live_baseline") if plan else None,
                  "before_after": state.get("live_before_after", "before"), "dependency": state.live_dependency,
                  "severity": state.live_severity / 100, "loss_limit": state.live_limit,
                  "locks": state.live_locks, "portfolio_sizes": None, "portfolio_error": None}
    opaque = [p["id"] for p in run.positions if any(n.meta.get("unmapped") for n in run.book.graphs[p["id"]].nodes())]
    return {"live": {"replay": bool(replay), "badge": "SAVED RUN · OFFLINE REPLAY" if replay else
                     "DELAYED API DATA" if delayed else "FRESH API OBSERVATIONS",
                     "can_rescue": status["execution_usable"], "can_edit": not replay,
                     "risk_only": not status["execution_usable"],
                     "note": "Historical observations; freshness checked at recorded time." if replay else
                     "Indicative model only · no transactions · costs and cash conversion assumed."},
            "ranking": ranking, "shared": [r for r in ranking if r["positions"] > 1 and r["kind"] != "chain"],
            "selected": selected, "stress": stress, "positions": run.positions, "state": state_view,
            "network": network(run.book, ranking, stress, state_view["revealed"], state_view["attacked"],
                               plan if state_view["before_after"] == "after" else None),
            "revision": revision(run), "scenario_revision": revision(run), "ack": state.get("live_last_event"),
            "execution_summary": {"available_options": sum(max(0, len(v)-1) for v in candidates["options"].values()),
                                  "unavailable_options": len(candidates["unavailable"])},
            "snapshot": utc(run.completed_at), "snapshot_window": status["as_of_window_utc"],
            "bundle_hash": digest(run.bundle), "quote_bundle": run.bundle, "opaque_positions": opaque,
            "challenge": {"supported": run.catalog, "step_usd": 50_000, "max_usd": 2_000_000}}


def settings():
    catalog = load_catalog()
    defaults = {p["id"]: p["size_usd"] for p in load_book()["positions"]}
    with st.expander("Portfolio & data settings"):
        st.button("Load $1M Hakutora live example", on_click=ui.load_hakutora_example, key="live_example",
                  help="Loads the example with strict 15-minute validation; click Fetch for new API data.")
        if "live_risk_age_minutes" not in st.session_state:
            st.session_state.live_risk_age_minutes = 60
        minutes = st.selectbox("Maximum risk-data age (minutes)", [15, 60], index=None,
                                key="live_risk_age_minutes", on_change=ui.clear_live_analysis)
        ids = st.multiselect("Live portfolio instruments (up to ten)", [p["id"] for p in catalog],
                              default=None if "live_selected" in st.session_state else list(defaults), key="live_selected",
                              format_func=lambda pid: next(p["label"] for p in catalog if p["id"] == pid))
        sizes = {p["id"]: st.number_input(p["label"], min_value=50_000, max_value=2_000_000,
                  value=defaults.get(p["id"], 500_000), step=50_000, key="live_size_"+p["id"])
                  if p["id"] in ids else 0 for p in catalog}
        grid = st.selectbox("Requested quote grid", ["25% steps (four per PT)", "5% steps (twenty per PT)",
                             "Risk only (no quotes)"], key="live_grid")
        st.caption("60 minutes permits clearly labelled delayed risk observations. Strict live validation is 15 minutes. "
                   "Execution marks, exact quotes and RPC expire after two minutes. Each quote covers only its exact size.")
    return resize_positions(catalog, sizes), grid, FreshnessPolicy(risk_seconds=minutes*60, max_skew_seconds=minutes*60)


def native_controls(run, analysis, ranking, status):
    """Accessible fallback and technical inspection; kept out of the main demo."""
    with st.expander("Advanced controls & raw evidence", expanded=st.query_params.get("fallback") == "1"):
        choices = {r["id"]: r for r in ranking}
        ui_dependency = st.selectbox("Attack dependency", list(choices), key="live_dependency",
                         format_func=lambda nid: choices[nid]["label"], on_change=ui.clear_live_analysis)
        st.slider("Intrinsic shock (%)", 0, 100, key="live_severity", on_change=ui.clear_live_analysis)
        cols = st.columns(3)
        cols[0].metric("Portfolio", f"${analysis['scenario']['aum_usd']:,.0f}")
        cols[1].metric("Conditional scenario loss", f"${analysis['scenario']['loss_usd']:,.2f}")
        cols[2].metric("Exposed positions", analysis["scenario"]["exposed_positions"])
        st.number_input("Maximum accounted scenario loss (USD)", min_value=0.0, step=50_000.0, key="live_limit",
                         on_change=ui.clear_live_analysis)
        st.multiselect("Lock positions", [p["id"] for p in run.positions], key="live_locks", on_change=ui.clear_live_analysis)
        if st.button("Calculate indicative model rescue", disabled=not status["execution_usable"], key="live_rescue"):
            try:
                calculate(run)
                st.rerun()
            except LiveInputError as exc:
                ui.clear_live_analysis()
                st.error(str(exc))
        st.json((st.session_state.get("live_analysis") or analysis).get("plan"))
        for assumption in ui.LIVE_ASSUMPTIONS:
            st.write("• " + assumption)
        st.json(run.mappings)
        st.json(run.bundle)
        if hasattr(run.client, "normalization"):
            st.json(run.client.normalization)


def receipt_download(run, analysis):
    rec = ui.observation_receipt(run, analysis)
    decision = (run.completed_at, None if analysis is None else
                (analysis["scenario"], analysis["exit_candidates"], analysis["plan"]))
    if st.session_state.get("live_receipt_decision") != decision:
        st.session_state.live_receipt_decision = decision
        st.session_state.live_download_receipt = rec
        try:
            st.session_state.live_receipt_path = ui.save_live_receipt(rec)
        except OSError:
            st.caption("Local saving is unavailable. The complete receipt can still be downloaded below.")
    rec = st.session_state.live_download_receipt
    st.download_button("Download live observation receipt", json.dumps(rec, indent=2, allow_nan=False),
                        file_name="blast-radius-replay-receipt.json" if getattr(run, "replay_context", None)
                        else "blast-radius-live-receipt.json", mime="application/json", key="live_download")
    st.caption("Replay verifies the recorded run. It does not make historical observations fresh or certify execution.")


@st.fragment(run_every="15s")
def render_live():
    state = st.session_state
    if state.pop("live_pending_replay", False):
        replay_saved()
    pending = state.pop("live_pending_action", None)
    if pending:
        apply_action(pending)
    st.markdown("<style>[data-testid=stHeader]{pointer-events:none!important}[data-testid=stToolbar]{display:none!important}</style>", unsafe_allow_html=True)
    st.caption("LIVE WORKSPACE · $1M Hakutora / cbBTC demo · fresh API data first, labelled saved replay if unavailable.")
    a, b, c = st.columns([1.2, 1.4, 1.2])
    a.button("Start live demo", type="primary", on_click=start_demo, key="live_start")
    fetch = b.button("Fetch fresh data & discover", key="live_refresh")
    c.button("Replay saved API run", on_click=replay_saved, key="live_saved")
    try:
        positions, grid, policy = settings()
    except ValueError as exc:
        st.error(str(exc))
        st.info("Start live demo or Replay saved API run restores a valid example. Snapshot Mode is also available above.")
        return
    demo = state.pop("live_start_requested", False)
    steps = list(range(1, 21)) if grid.startswith("5%") else [] if grid.startswith("Risk") else [5, 10, 15, 20]
    if fetch or demo:
        state.pop("live_run", None)
        state.live_replay = False
        state.live_notice = None
        reset_stages()
        with st.spinner("Checking Morpho / Pendle observations and rebuilding the dependency graph…"):
            try:
                run = ui.capture_live(positions, quote_steps=steps, client=ui.ObservationClient(policy=policy))
                state.live_run = run
                try:
                    ui.save_live_receipt(ui.observation_receipt(run))
                except OSError:
                    pass  # The download remains available even on a read-only filesystem.
                if demo and not run.freshness()["execution_usable"]:
                    state.live_fetch_issue = run.freshness()["risk_error"] or "; ".join(run.freshness()["execution_errors"])
                    state.live_pending_replay = True
                    st.rerun()
            except (LiveInputError, OSError, ValueError, KeyError, TypeError) as exc:
                state.live_notice = "The API request could not be completed. " + str(exc)
                if demo:
                    state.live_fetch_issue = str(exc)
                    state.live_pending_replay = True
                    st.rerun()
    run = state.get("live_run")
    if state.get("live_notice"):
        st.info(state.live_notice)
    if run is None:
        st.markdown("### Trace the risk. Test the shock. Price the protection.")
        st.write("Choose **Start live demo**, then use the same graph and controls as Snapshot Mode. "
                 "The saved API run works without internet; its original timestamps stay visible.")
        st.caption(f"Configured portfolio: {len(positions)} instruments · ${sum(p['size_usd'] for p in positions):,.0f} hypothetical allocation.")
        return
    changed = run.positions != positions or run.quote_steps != steps or run.client.policy != policy
    status = run.freshness()
    risk_status = ui.risk_data_status(status)
    replay = getattr(run, "replay_context", None)
    if replay:
        st.warning("HISTORICAL REPLAY · saved real API observations · recorded " + replay["recorded_decision_utc"][:19].replace("T", " ")
                   + " UTC. Not current live data. Freshness is validated at that recorded time; no network is required.")
        if state.get("live_fetch_issue"):
            with st.expander("Why the fresh request could not be used"):
                st.write(state.live_fetch_issue)
    elif risk_status["classification"] == "delayed risk observations":
        st.warning(f"Delayed risk data: oldest validated state is {risk_status['maximum_observed_risk_age_seconds']/60:.1f} "
                   "minutes old. Accepted under the selected window; strict 15-minute live validation has not passed.")
    elif status["risk_usable"]:
        st.caption("✓ Fresh API risk observations passed strict 15-minute validation · hypothetical scenario · no transactions.")
    window_label = "As-of provider state window (UTC): " if status["risk_usable"] else "Validated provider timestamps only (partial; analysis rejected): "
    st.caption(window_label + (" → ".join(status["as_of_window_utc"]) or "none") + " · retrieved through " + utc(run.completed_at))
    if changed or not status["risk_usable"]:
        ui.clear_live_analysis()
        if changed:
            st.warning("Portfolio or quote grid changed. Refresh before analysis." if run.client.policy == policy else
                       "Risk-data age policy changed. Fetch a new run before analysis.")
            st.error("Live analysis rejected. Portfolio, quote grid or risk-data policy changed; fetch a new run.")
        else:
            ui.render_rejection(run, status)
        st.info("Continue immediately with Replay saved API run, or use offline Snapshot Mode above. Both retain their recorded-data labels.")
        receipt_download(run, None)
        return
    ranking = discover(run.book)
    shared = [r for r in ranking if r["positions"] > 1 and r["kind"] != "chain"]
    if state.get("live_dependency") not in {r["id"] for r in ranking}:
        state.live_dependency = (shared or ranking)[0]["id"]
    state.setdefault("live_severity", 100)
    state.setdefault("live_limit", 500_000.0)
    state.live_locks = [pid for pid in state.get("live_locks", []) if pid in {p["id"] for p in positions}]
    try:
        analysis = ui.analyze_live(run, state.live_dependency, state.live_severity/100,
                                   loss_limit=state.live_limit, locks=state.live_locks)
    except LiveInputError as exc:
        ui.clear_live_analysis()
        st.error(str(exc))
        st.info("Replay saved API run or switch to Snapshot Mode to continue without the API.")
        receipt_download(run, None)
        return
    if not status["execution_usable"]:
        ui.clear_live_analysis()
        st.warning("Risk-only analysis. Rescue is unavailable for this capture: " + "; ".join(
            status["execution_errors"] + [r["reason"] for r in status["rejections"]]))
    if state.get("live_analysis"):
        show_note = st.warning if st.query_params.get("fallback") == "1" else st.caption
        show_note(("Historical replay model rescue" if replay else "Delayed-data indicative model rescue" if
                    risk_status["classification"] == "delayed risk observations" else "Indicative model rescue")
                   + " · financial constraints checked · no transactions · withdrawal and cash conversion unverified.")
    if st.query_params.get("fallback") != "1":
        result = render_terminal(payload(run, analysis, ranking, status), key="live_terminal")
        event = result.action
        if event and event.get("nonce") != state.get("live_last_event"):
            state.live_pending_action = event
            st.rerun()
    with st.expander("Sources, timestamps and freshness checks"):
        st.json(risk_status)
        st.json(status)
    native_controls(run, analysis, ranking, status)
    receipt_download(run, state.get("live_analysis") or analysis)
