"""Run a real, bounded live fire drill and save its observations and result."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from blast_radius.fire_drill.catalog import load_catalog
from blast_radius.fire_drill.live import analyze_live
from app.live_data import capture_live, live_receipt, save_live_receipt, verify_live_receipt
from blast_radius.fire_drill.model import discover
from blast_radius.sources.live import utc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", nargs="+", default=["hakutora-usdc"])
    parser.add_argument("--dependency")
    parser.add_argument("--loss-limit", type=float, default=500_000)
    args = parser.parse_args()
    catalog = load_catalog()
    unknown = set(args.positions) - {p["id"] for p in catalog}
    if unknown:
        parser.error("Unadmitted positions: " + ", ".join(sorted(unknown)))
    positions = [p for p in catalog if p["id"] in args.positions]
    run = capture_live(positions)
    status = run.freshness()
    analysis = None
    ranking = []
    if status["risk_usable"] and status["execution_usable"]:
        ranking = discover(run.book)
        dependency = args.dependency or next(r["id"] for r in ranking if r["kind"] != "chain")
        analysis = analyze_live(run, dependency, 1, loss_limit=args.loss_limit, rescue=True)
    rec = live_receipt(run, analysis)
    path = save_live_receipt(rec)
    verify_live_receipt(rec)
    plan = (analysis or {}).get("plan") or {}
    successful = bool(analysis and plan.get("audit", {}).get("verified") and plan.get("target_met"))
    summary = {"successful": successful, "receipt": str(path.relative_to(ROOT)),
               "receipt_sha256": rec["receipt_sha256"], "receipt_replay_passed": True,
               "source": "real HTTP requests; no mocks or historical response-cache reads",
               "capture_started_utc": utc(run.client.started_at), "capture_completed_utc": utc(run.completed_at),
               "positions": positions, "morpho_discovery_scope": rec["morpho_discovery_scope"],
               "ranking": ranking, "freshness": (analysis or {}).get("freshness", status),
               "scenario": (analysis or {}).get("scenario"), "plan": plan or None,
               "source_requests": [{"url": o["request"]["url"], "method": o["request"]["method"],
                                    "requested_utc": utc(o["requested_at"]), "received_utc": utc(o["received_at"]),
                                    "http_status": o.get("http_status"), "key": o["key"]}
                                   for o in run.client.observations],
               "assumptions": rec["assumptions"], "vault_observations": list(run.vault_records.values())}
    out = ROOT / "artifacts/live" / ("successful_live_analysis.json" if successful else "rejected_live_analysis.json")
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in
                      ("ranking", "vault_observations", "assumptions", "source_requests")}, indent=2))
    print("Report:", out)
    return 0 if successful else 2


if __name__ == "__main__":
    raise SystemExit(main())
