"""Emit modified-book decisions for a separate raw-data/Decimal audit."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["BLAST_RADIUS_OFFLINE"] = "1"

from blast_radius.fire_drill.challenge import resize_positions
from blast_radius.fire_drill.evidence import receipt, source_manifest
from blast_radius.fire_drill.execution import exit_options, load_execution
from blast_radius.fire_drill.model import prepare, stress_book
from blast_radius.fire_drill.optimize import plan_rescue
from blast_radius.portfolio.book import load_book

WSTETH = "token:ethereum:0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0"
CASES = {
    "resized": {"pt-wsteth": 750_000, "steakhouse-eth": 500_000, "steakhouse-usdt": 1_250_000, "pt-susde": 1_000_000},
    "removed": {"steakhouse-eth": 500_000, "steakhouse-usdt": 1_250_000, "pt-susde": 1_000_000},
    "quote_bound": {"pt-wsteth": 2_000_000, "steakhouse-eth": 500_000, "pt-susde": 1_000_000},
}


def main():
    supported = load_book()["positions"]
    bundle, manifest = load_execution(), source_manifest()
    for name, allocations in CASES.items():
        book = prepare(resize_positions(supported, {p["id"]: allocations.get(p["id"], 0) for p in supported}))
        stress, execution = stress_book(book, WSTETH), exit_options(book, bundle)
        plan = plan_rescue(stress, execution, 500_000)
        document = receipt(stress, execution, plan, manifest, bundle, positions=book.positions)
        (ROOT / f"artifacts/challenge_{name}_receipt.json").write_text(json.dumps(document, indent=2), encoding="utf-8")
        print(f"{name}: {plan['status']}; ${stress['aum_usd']:,.0f} book; ${plan['audit']['accounted_loss_usd']:,.2f} accounted loss")


if __name__ == "__main__":
    main()
