"""Native live workflow; snapshot presentation stays independent and offline."""
from __future__ import annotations

import json
import time

import streamlit as st

from blast_radius.fire_drill.catalog import load_catalog
from blast_radius.fire_drill.challenge import resize_positions
from blast_radius.fire_drill.live import LIVE_ASSUMPTIONS, analyze_live
from app.live_data import capture_live, live_receipt, save_live_receipt
from blast_radius.fire_drill.model import discover
from blast_radius.fire_drill.presentation import network
from blast_radius.portfolio.book import load_book
from blast_radius.sources.live import FreshnessPolicy, LiveInputError, ObservationClient, digest, timestamp, utc


def snapshot_fallback():
    st.session_state.data_mode = "Snapshot Mode"


def clear_live_analysis():
    st.session_state.pop("live_analysis", None)
    st.session_state.pop("live_baseline", None)
    st.session_state.live_before_after = "before"


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
    st.session_state.live_revealed = st.session_state.live_attacked = st.session_state.live_evidence = False
    st.session_state.live_last_event = None


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
    if getattr(run, "replay_context", None):
        rec["presentation_context"] = dict(run.replay_context)
        rec["classification"] = "historical replay of " + rec["risk_data_status"]["classification"] + "; not current live data"
    rec.pop("receipt_sha256")
    rec["receipt_sha256"] = digest(rec)
    return rec


def rejected_morpho_inputs(run, status):
    """Describe rejected identities from the captured data, without accepting them."""
    reasons = " ".join([status["risk_error"] or ""] +
                       [r["reason"] for r in status["rejections"] if r["kind"] == "risk"]).lower()
    if "stale or future " not in reasons:
        return []  # Balance/identity errors must not be described as old timestamps.
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


def render_live():
    from app.components.live_workspace import render_live as workspace
    workspace()
