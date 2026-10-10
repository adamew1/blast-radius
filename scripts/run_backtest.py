"""Run the frozen contagion backtest over the whole event library + false-alarm controls, and
write artifacts/backtest_results.json. Reuses the production engine (propagate + decide).

Online on first run (fetches calm-2024 control series); offline-safe afterwards from data/raw/.
Run:  .venv/Scripts/python.exe scripts/run_backtest.py
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from blast_radius.backtest.controls import false_alarm_test  # noqa: E402
from blast_radius.backtest.library import events, load_rule  # noqa: E402
from blast_radius.backtest.runner import run_event  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def _compact_series(rows: list[dict], up_ref: float, dn_ref: float) -> dict:
    """Trim the per-timestep rows to compact arrays for the per-event chart."""
    def iso(ts):
        return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
    out = {"t": [], "up_pct": [], "dn_pct": []}
    for r in rows:
        out["t"].append(iso(r["ts"]))
        out["up_pct"].append(round(100 * r["up"] / up_ref, 2) if (r["up"] and up_ref) else None)
        out["dn_pct"].append(round(100 * r["dn"] / dn_ref, 2) if (r["dn"] and dn_ref) else None)
    return out


def _summarise(evs: list[dict]) -> dict:
    hits = [e for e in evs if e["hit"]]
    leads = [e["lead_hours"] for e in hits if e["lead_hours"] is not None]
    saved = [e["saved_vs_naive_usd"] for e in evs if e["saved_vs_naive_usd"] is not None]
    avoided = [e["loss_avoided_vs_hold_usd"] for e in evs if e["loss_avoided_vs_hold_usd"] is not None]
    return {
        "events_total": len(evs),
        "events_caught": len(hits),
        "simultaneous_signals": sum(bool(e.get("simultaneous")) for e in evs),
        "misses": len(evs) - len(hits),
        "scored_savings_pairs": len(saved),
        "median_lead_hours": round(statistics.median(leads), 1) if leads else None,
        "max_lead_hours": max(leads) if leads else None,
        "total_saved_vs_naive_usd": round(sum(saved)) if saved else 0,
        "total_loss_avoided_vs_hold_usd": round(sum(avoided)) if avoided else 0,
    }


def main() -> None:
    cfg = load_rule()
    all_events = events()
    print(f"Running {len(all_events)} events through the frozen rule...")
    results = []
    for ev in all_events:
        r = run_event(ev)
        r_full_series = r.pop("series")
        r["chart"] = _compact_series(r_full_series, r["up_ref"], r["dn_ref"])
        results.append(r)
        print(f"  [{'HIT ' if r['hit'] else 'MISS'}] {r['id']:<18} lead={r['lead_hours']}h "
              f"saved=${r['saved_vs_naive_usd']}")

    dev = [r for r in results if r["cohort"] == "development"]
    oos = [r for r in results if r["cohort"] != "development"]
    headline = {"without_stream": _summarise(oos), "with_stream": _summarise(results),
                "development_case": _summarise(dev)}

    def year(r):
        return int(r["date"][:4])
    split = {"pre_2024": _summarise([r for r in oos if year(r) < 2024]),
             "y2024_2025": _summarise([r for r in oos if year(r) >= 2024])}

    print("Running false-alarm controls over calm 2024 (non-development pairs)...")
    pairs = [ev for ev in all_events if ev["cohort"] != "development"]
    fa_rows = [false_alarm_test(p) for p in pairs]
    for row in fa_rows:
        print(f"  {row['pair']:<24} " + (
            f"episodes={row['n_exit_episodes']} false_alarms={row['false_alarms']} "
            f"/pair-yr={row['false_alarms_per_pair_year']}" if row.get("available")
            else f"(unavailable: {row.get('note')})"))
    avail = [r for r in fa_rows if r.get("available")]
    total_fa = sum(r["false_alarms"] for r in avail)
    total_py = sum(r["pair_years"] for r in avail)

    def _grp(kind):
        g = [r for r in avail if r.get("upstream_kind") == kind]
        fa = sum(r["false_alarms"] for r in g)
        py = sum(r["pair_years"] for r in g)
        return {"n_pairs": len(g), "false_alarms": fa, "pair_years": py,
                "per_pair_year": round(fa / py, 3) if py else None}

    false_alarms = {"pairs": fa_rows, "total_false_alarms": total_fa, "total_pair_years": total_py,
                    "per_pair_year": round(total_fa / total_py, 3) if total_py else None,
                    "n_pairs": len(avail),
                    "by_upstream_kind": {"stablecoin": _grp("stablecoin"), "volatile": _grp("volatile")}}

    out = {
        "generated_at_note": "numbers computed by code from cached real DefiLlama data",
        "rule": cfg,  # the frozen signal rule, echoed in
        "triggers": sorted({r["trigger"] for r in results}),
        "n_events": len(results), "n_triggers_out_of_sample": len({r["trigger"] for r in oos}),
        "headline": headline, "split": split, "false_alarms": false_alarms,
        "events": results, "rule_vs_ml": None,
        "scoring_notes": ["Catch requires EXIT strictly BEFORE the downstream break; same-bar signals count as misses.",
                          "Observations are available at the END of their 4h bucket; no future denominator observations.",
                          "References freeze at the event date, and signals are scored from that date onward.",
                          "Savings include ALL pairs, including misses. With no EXIT, use observed worst-14d hold mark; this is not realized P&L.",
                          "1% exit cost applies to sale proceeds for both strategies; $1M starting notional per pair.",
                          "Pairs were selected retrospectively for data and visible breaks; this is not a prospective out-of-sample validation.",
                          "Six non-development pairs share two crises; lead times are uncertain within the 4h sampling interval.",
                          "Stablecoin/volatile control breakdown was added after seeing results; overall rate is primary."],
    }
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / "backtest_results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    h = headline["without_stream"]
    sc = false_alarms["by_upstream_kind"]["stablecoin"]
    vo = false_alarms["by_upstream_kind"]["volatile"]
    print(f"\n=== HEADLINE (without Stream dev case) ===")
    print(f"caught {h['events_caught']}/{h['events_total']} | median lead {h['median_lead_hours']}h "
          f"(max {h['max_lead_hours']}h) | saved vs naive ${h['total_saved_vs_naive_usd']:,}")
    print(f"Overall false alarms/pair-year: {false_alarms['per_pair_year']} "
          f"over {false_alarms['total_pair_years']:.3f} observed pair-years")
    print(f"false alarms/pair-year: stablecoin-upstream {sc['per_pair_year']} ({sc['n_pairs']} pairs); "
          f"volatile-token proxy {vo['per_pair_year']} ({vo['n_pairs']} pair) -- too noisy to trade")
    print("wrote artifacts/backtest_results.json")


if __name__ == "__main__":
    main()
