"""Recompute presentation headlines and a complete reproducible decision receipt."""
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["BLAST_RADIUS_OFFLINE"] = "1"

from blast_radius.fire_drill.evidence import receipt, source_manifest
from blast_radius.fire_drill.execution import exit_options, load_execution
from blast_radius.fire_drill.model import prepare, discover, stress_book
from blast_radius.fire_drill.optimize import plan_rescue
from blast_radius.portfolio.book import load_book


def main():
    b = prepare(load_book()["positions"])
    start = time.perf_counter()
    ranking = discover(b)
    discovery_seconds = time.perf_counter() - start
    shared = [r for r in ranking if r["positions"] > 1 and r["kind"] != "chain"]
    bundle = load_execution()
    execution = exit_options(b, bundle)
    cases = []
    for dependency, locks in ((shared[0]["id"], []), (shared[0]["id"], ["pt-wsteth"]),
                              ("issuer:lido", []), ("issuer:lido", ["pt-wsteth"])):
        start = time.perf_counter()
        stress = stress_book(b, dependency)
        stress_seconds = time.perf_counter() - start
        start = time.perf_counter()
        plan = plan_rescue(stress, execution, 500000, locks)
        solve_seconds = time.perf_counter() - start
        cases.append({"dependency": dependency, "locks": locks, "stress": stress, "plan": plan,
                      "stress_seconds": stress_seconds, "solve_seconds": solve_seconds})
    data = {"discovery_seconds": discovery_seconds, "ranking": ranking, "cases": cases,
            "quote_options_available": sum(o.get("available",False) for p in bundle["positions"].values() for o in p["options"]),
            "cash_conversion_bps_assumed": 10, "gas_bps_assumed": 2,
            "data_classification": "frozen API, manual mapping and RPC observations; modelled hypothetical loss"}
    (ROOT / "artifacts/fire_drill.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    case = cases[0]
    rec = receipt(case["stress"], execution, case["plan"], source_manifest(), bundle)
    (ROOT / "artifacts/fire_drill_receipt.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
    r = case["plan"]["audit"]
    headline = f"Computed weakest shared dependency: {shared[0]['label']} across {shared[0]['positions']} positions. "
    headline += f"Conditional loss ${case['stress']['loss_usd']:,.0f}; $500,000 protection limit; "
    headline += f"accounted loss ${r['accounted_loss_usd']:,.0f}; economic cost ${r['protection_cost_usd']:,.0f}; "
    headline += f"break-even scenario probability {r['break_even_probability']:.2%} over 30 days. "
    headline += "Hypothetical pre-failure protection, 5% grid, snapshot liquidity bounds, explicit recovery and cash-conversion assumptions."
    (ROOT / "artifacts/fire_drill_pitch.txt").write_text(headline + "\n", encoding="utf-8")
    print(headline)
    print(f"Discovery {discovery_seconds:.3f}s; stress {case['stress_seconds']:.3f}s; optimization {case['solve_seconds']:.3f}s")


if __name__ == "__main__":
    main()
