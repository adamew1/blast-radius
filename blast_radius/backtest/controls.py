"""False-alarm control test: run the identical frozen rule over calm 2024 for each pair, using a
rolling 7-day median reference (so the rule works the same outside event windows). Count EXIT
episodes that are NOT followed by a real >5% downstream break within 14 days -> false alarms/pair-year.

2024 contains none of our events, so no exclusion windows are needed."""
from __future__ import annotations

from .graph import build_event_graph
from .library import load_rule
from .prices import DAY, forward_fill, load_leg, median
from .runner import _decider, shock_from

_SEC = {"1h": 3600, "4h": 4 * 3600, "1d": DAY}


def _rolling_ref(series: dict[int, float], t: int, days: int) -> float | None:
    lo = t - days * DAY
    return median([v for ts, v in series.items() if lo <= ts < t])


def false_alarm_test(pair: dict) -> dict:
    cfg = load_rule()
    rule, out, ctrl = cfg["rule"], cfg["outcome"], cfg["controls"]
    period = cfg["data"]["granularity"]
    sec = _SEC[period]
    ref_days = cfg["reference"]["control_rolling_median_days"]
    brk = 1.0 - out["break_threshold_pct"] / 100.0
    gate = rule["shock_gate_pct"]
    year = ctrl["year"]

    import datetime as dt
    start = int(dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    span = 366 * (DAY // sec)

    try:
        up_raw = load_leg(pair["upstream"]["price_key"], pair["upstream"].get("denom", "usd"), start, span, period)
        dn_raw = load_leg(pair["downstream"]["price_key"], pair["downstream"].get("denom", "usd"), start, span, period)
    except Exception as e:  # noqa: BLE001
        return {"id": pair["id"], "pair": f"{pair['upstream']['label']}->{pair['downstream']['label']}",
                "available": False, "note": repr(e)[:120]}
    if len(up_raw) < 30 or len(dn_raw) < 30:
        return {"id": pair["id"], "pair": f"{pair['upstream']['label']}->{pair['downstream']['label']}",
                "available": False, "note": f"insufficient {year} data (up={len(up_raw)}, dn={len(dn_raw)})"}

    ts = sorted(set(up_raw) | set(dn_raw))
    up = forward_fill(up_raw, ts)
    dn = forward_fill(dn_raw, ts)

    g = build_event_graph(pair)
    run = _decider(g, rule)

    exit_ts: list[int] = []
    # Require a full reference window and a full observed 14-day follow-up. Do not call
    # late-December episodes false alarms merely because January is absent from cache.
    past_steps = range(1, ref_days * DAY // sec + 1)
    future_steps = range(1, out["outcome_window_days"] * DAY // sec + 1)
    eligible = [t for t in ts if t in up and t in dn and
                all(t-k*sec in up and t-k*sec in dn for k in past_steps) and
                all(t+k*sec in dn for k in future_steps)]
    for t in eligible:
        ref = _rolling_ref(up, t, ref_days)
        if not ref:
            continue
        shock = shock_from(up.get(t), ref, gate)
        if run(shock)["verdict"] == "EXIT":
            exit_ts.append(t)

    # group EXIT timestamps into episodes separated by >24h of calm
    episodes: list[int] = []
    last = None
    for t in exit_ts:
        if last is None or t - last > DAY:
            episodes.append(t)
        last = t

    # an episode is a FALSE alarm if the downstream does NOT break >5% (vs its rolling ref)
    # within outcome_window_days after the episode start
    false_alarms = 0
    for e in episodes:
        dref = _rolling_ref(dn, e, ref_days) or (dn.get(e))
        broke = any(dn.get(t) is not None and dref and dn[t] < brk * dref
                    for t in ts if e <= t <= e + out["outcome_window_days"] * DAY)
        if not broke:
            false_alarms += 1

    days_covered = len(eligible) * sec / DAY
    pair_years = days_covered / 365.0
    return {
        "id": pair["id"], "pair": f"{pair['upstream']['label']}->{pair['downstream']['label']}",
        "upstream_kind": pair["upstream"].get("kind", "unknown"),
        "available": bool(pair_years), "year": year, "pair_years": pair_years,
        "evaluation_days": days_covered,
        "right_censored_days": out["outcome_window_days"],
        "coverage_note": "Only timestamps with complete aligned reference and downstream follow-up windows count; missing intervals are not calm observations.",
        "n_exit_episodes": len(episodes), "false_alarms": false_alarms,
        "false_alarms_per_pair_year": round(false_alarms / pair_years, 2) if pair_years else None,
    }
