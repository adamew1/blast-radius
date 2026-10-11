"""Verify a downloaded decision against its candidates and local evidence files."""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["BLAST_RADIUS_OFFLINE"] = "1"
from blast_radius.fire_drill.optimize import verify_plan
from blast_radius.fire_drill.model import prepare, stress_book
from blast_radius.fire_drill.execution import exit_options, load_execution
from blast_radius.fire_drill.challenge import resize_positions
from blast_radius.fire_drill.catalog import execution_for, load_catalog
from blast_radius.portfolio.book import load_book


def verify(path):
    rec = json.loads(Path(path).read_text(encoding="utf-8"))
    if rec.get("receipt_schema") in ("blast-radius-live-v1", "blast-radius-native-live-v2"):
        from app.live_data import verify_live_receipt
        verify_live_receipt(rec)
        if "risk_data_status" in rec:
            status = rec["analysis"]["freshness"] if rec["analysis"] else rec["freshness_at_capture"]
            checks = [c for c in status["checks"] if c["kind"] == "risk"]
            age = max((c["age_seconds"] for c in checks), default=0)
            times = [c["observed_at"] for c in checks]
            spread = max(times) - min(times) if times else 0
            delayed = age > 900 or spread > 900
            classification = "rejected" if not status["risk_usable"] else "delayed risk observations" if delayed else "fresh risk observations"
            expected = {"classification": classification,
                        "strict_15_minute_risk_passed": bool(status["risk_usable"] and not delayed),
                        "maximum_observed_risk_age_seconds": age, "risk_timestamp_spread_seconds": spread,
                        "selected_risk_age_limit_seconds": rec["policy"]["risk_seconds"],
                        "selected_risk_spread_limit_seconds": rec["policy"]["max_skew_seconds"]}
            if rec["risk_data_status"] != expected:
                raise ValueError("Risk-data classification does not reproduce")
            expected_label = {"delayed risk observations": "delayed protocol observations; indicative analysis, not verified fresh live data",
                              "rejected": "rejected protocol observations; no verified current analysis",
                              "fresh risk observations": "fresh protocol observations with manual mappings and financial assumptions"}[classification]
            if rec["classification"] != expected_label:
                raise ValueError("Receipt classification does not reproduce")
            print(f"PASS embedded observations, historical policy checks, scenario and plan audit: {classification} (not executable)")
        else:
            print("PASS embedded live observations, historical freshness, scenario, candidates and plan audit (not executable)")
        return
    for r in rec["evidence"]["sources"]:
        if hashlib.sha256((ROOT / r["path"]).read_text(encoding="utf-8").encode()).hexdigest() != r["sha256"]:
            raise ValueError(f"Evidence differs: {r['path']}")
    for name, digest in rec["evidence"]["files"].items():
        p = ROOT / name
        raw = p.read_text(encoding="utf-8").encode()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError(f"Source differs: {name}")
    # Independently recompute both the scenario and the candidate costs, rather
    # than accepting totals embedded in the downloaded receipt.
    supported = load_book()["positions"]
    positions = supported
    if rec["receipt_schema"] == "blast-radius-decision-v3":
        supported = load_catalog()
    if rec["receipt_schema"] in ("blast-radius-decision-v2", "blast-radius-decision-v3"):
        submitted = rec["portfolio"]
        sizes = {p["id"]: 0 for p in supported}
        sizes.update({p["id"]: p["size_usd"] for p in submitted})
        positions = resize_positions(supported, sizes)
        if positions != submitted:
            raise ValueError("Receipt changes supported instrument identity or duplicates a position")
    elif rec["receipt_schema"] != "blast-radius-decision-v1":
        raise ValueError("Unknown receipt schema")
    book = prepare(positions)
    recomputed = stress_book(book, rec["scenario"]["dependency_id"], rec["scenario"]["severity"])
    if recomputed != rec["scenario"]:
        raise ValueError("Scenario values do not reproduce")
    expected_bundle = execution_for(positions) if rec["receipt_schema"] == "blast-radius-decision-v3" else load_execution()
    if rec["quote_bundle"] != expected_bundle:
        raise ValueError("Quote bundle differs from frozen evidence")
    for record in rec["quote_bundle"]["positions"].values():
        out = record["output_asset"]
        for q in record["options"]:
            if not q["available"]:
                continue
            raw = json.loads((ROOT / "data/raw" / (q["raw_cache_key"] + ".json")).read_text(encoding="utf-8"))
            if raw["data"]["data"]["amountOut"] != q["amount_out"] or raw["meta"]["params"] != q["params"]:
                raise ValueError("Candidate differs from original API quote")
            value = int(q["amount_out"]) / 10 ** out["decimals"] * out["price_usd"]
            if abs(value - q["output_value_usd"]) > .02 or abs(max(0, q["notional_usd"]-value)-q["mark_shortfall_usd"]) > .02:
                raise ValueError("Candidate quote valuation does not reproduce")
    candidates = exit_options(book, rec["quote_bundle"], rec["exit_candidates"]["carry_days"])
    if candidates != rec["exit_candidates"]:
        raise ValueError("Exit candidates and market capacities do not reproduce")
    plan = rec["plan"]
    if plan and plan.get("audit"):
        audit = verify_plan(rec["scenario"], rec["exit_candidates"], plan["actions"], plan["withdrawals"],
                            plan["locks"], plan["loss_limit_usd"])
        for key in ("avoided_loss_usd", "residual_loss_usd", "protection_cost_usd", "accounted_loss_usd"):
            if abs(audit[key] - plan["audit"][key]) > .02:
                raise ValueError(f"Reported total differs: {key}")
        print(f"PASS source hashes, scenario, quote valuations, candidates and plan: ${audit['accounted_loss_usd']:,.2f} accounted loss")
    else:
        print("PASS evidence hashes; receipt has no audited plan")


if __name__ == "__main__":
    verify(sys.argv[1] if len(sys.argv)>1 else ROOT / "artifacts/fire_drill_receipt.json")
