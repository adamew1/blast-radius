"""Run one event through the frozen rule and compute per-event metrics.

The signal uses ONLY the upstream price at each timestamp (forced into the engine). The downstream
price is used solely to score the outcome (did it break? how much loss was avoided?). Identical
treatment for every event; nothing is tuned here."""
from __future__ import annotations

from ..risk.decision import decide
from ..risk.propagate import propagate
from .graph import UPSTREAM_ID, build_event_graph
from .library import load_rule
from .prices import DAY, date_of, event_window

POSITION_USD = 1_000_000


def shock_from(up_px: float | None, up_ref: float | None, gate: float) -> float:
    if not up_px or not up_ref:
        return 0.0
    s = max(0.0, 1.0 - up_px / up_ref)
    return s if s > gate else 0.0


def _decider(g, rule: dict):
    """Memoised decide() over rounded shock (collapses the many zero-shock calm steps)."""
    cache: dict[float, dict] = {}

    def run(shock: float) -> dict:
        k = round(shock, 4)
        if k not in cache:
            force = {UPSTREAM_ID: {"prob": 1.0, "severity": k}} if k > 0 else None
            res = propagate(g, rule["horizon_months"], n_paths=rule["n_paths"],
                            seed=rule["seed"], force=force)
            dec = decide(g, res, {"cost_pct": rule["exit_cost_pct"]},
                         apy=rule["apy"], horizon_months=rule["horizon_months"])
            cache[k] = {"verdict": dec["verdict"], "el": dec["el"], "cvar95": dec["cvar95"]}
        return cache[k]

    return run


def run_event(event: dict) -> dict:
    cfg = load_rule()
    rule, out = cfg["rule"], cfg["outcome"]
    gate = rule["shock_gate_pct"]
    brk = 1.0 - out["break_threshold_pct"] / 100.0
    win = event_window(event)
    ts, up, dn, up_ref, dn_ref = win["ts"], win["up"], win["dn"], win["up_ref"], win["dn_ref"]

    g = build_event_graph(event)
    run = _decider(g, rule)

    signal_ts = None
    rows = []
    for t in ts:
        up_px, dn_px = up.get(t), dn.get(t)
        shock = shock_from(up_px, up_ref, gate)
        d = run(shock)
        if d["verdict"] == "EXIT" and signal_ts is None:
            signal_ts = t
        rows.append({"ts": t, "up": up_px, "dn": dn_px, "shock": shock,
                     "verdict": d["verdict"], "el": d["el"]})

    # downstream break = first timestamp the downstream is >5% below its reference
    break_ts = next((t for t in ts if dn.get(t) is not None and dn_ref and dn[t] < brk * dn_ref), None)

    hit = bool(signal_ts is not None and break_ts is not None and signal_ts <= break_ts)
    lead_hours = round((break_ts - signal_ts) / 3600.0, 1) if hit else None

    anchor = signal_ts or break_ts or win["event_ts"]
    worst = None
    if dn_ref:
        in14 = [dn[t] for t in ts if anchor <= t <= anchor + out["outcome_window_days"] * DAY and dn.get(t) is not None]
        worst = min(in14) if in14 else None

    dn_sig = dn.get(signal_ts) if signal_ts else None
    dn_brk = dn.get(break_ts) if break_ts else None
    ec = rule["exit_cost_pct"]

    def loss_usd(px):
        return POSITION_USD * (1.0 - px / dn_ref) + ec * POSITION_USD if (px and dn_ref) else None

    # loss avoided by exiting on signal vs riding the position to its worst point in 14 days
    loss_avoided_vs_hold = None
    if dn_sig and worst and dn_ref:
        loss_avoided_vs_hold = POSITION_USD * (dn_sig * (1 - ec) - worst) / dn_ref
    tool_loss = loss_usd(dn_sig)
    naive_loss = loss_usd(dn_brk)
    saved_vs_naive = (naive_loss - tool_loss) if (tool_loss is not None and naive_loss is not None) else None

    return {
        "id": event["id"], "name": event["name"], "date": event["date"],
        "trigger": event["trigger"], "cohort": event["cohort"], "dep_type": event["dep_type"],
        "exposure_pct": event["exposure_pct"], "estimated": event.get("estimated", False),
        "exposure_source": event.get("exposure_source", ""),
        "upstream": event["upstream"]["label"], "downstream": event["downstream"]["label"],
        "denom": event["downstream"].get("denom", "usd"), "sources": event.get("sources", []),
        "up_ref": _r(up_ref), "dn_ref": _r(dn_ref),
        "signal_ts": signal_ts, "signal_date": date_of(signal_ts) if signal_ts else None,
        "break_ts": break_ts, "break_date": date_of(break_ts) if break_ts else None,
        "hit": hit, "lead_hours": lead_hours,
        "dn_at_signal": _r(dn_sig), "dn_at_break": _r(dn_brk), "dn_worst_14d": _r(worst),
        "loss_avoided_vs_hold_usd": _ri(loss_avoided_vs_hold),
        "tool_realized_loss_usd": _ri(tool_loss), "naive_realized_loss_usd": _ri(naive_loss),
        "saved_vs_naive_usd": _ri(saved_vs_naive),
        "series": rows,
    }


def _r(x, dp=6):
    return round(x, dp) if isinstance(x, (int, float)) else None


def _ri(x):
    return round(x) if isinstance(x, (int, float)) else None
