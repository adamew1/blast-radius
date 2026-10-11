"""Construct a book containing only new instruments and exercise three shocks."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["BLAST_RADIUS_OFFLINE"] = "1"
from blast_radius.fire_drill.catalog import load_catalog, execution_for
from blast_radius.fire_drill.challenge import resize_positions
from blast_radius.fire_drill.evidence import receipt, source_manifest
from blast_radius.fire_drill.model import prepare, stress_book
from blast_radius.fire_drill.execution import exit_options
from blast_radius.fire_drill.optimize import plan_rescue
from blast_radius.portfolio.book import load_book


def main():
    catalog = load_catalog()
    original_ids = {p["id"] for p in load_book()["positions"]}
    positions = [p for p in catalog if p["id"] not in original_ids]
    sizes = {p["id"]: (750_000 if "4a5067" in p["id"] else 500_000) if p in positions else 0 for p in catalog}
    book = prepare(resize_positions(catalog, sizes))
    bundle = execution_for(book.positions)
    execution, manifest = exit_options(book, bundle), source_manifest()
    targets = {"wsteth": "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0",
               "apyusd": "0x38eeb52f0771140d10c4e9a9a72349a329fe8a6a",
               "usd3": "0x056b269eb1f75477a8666ae8c7fe01b64dd55ecc"}
    for name, target in targets.items():
        stress = stress_book(book, "token:ethereum:" + target)
        plan = plan_rescue(stress, execution, 200_000)
        rec = receipt(stress, execution, plan, manifest, bundle, positions=book.positions, catalog_mode=True)
        (ROOT / f"artifacts/catalog_{name}_receipt.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
        print(f"{name}: {plan['status']}; ${stress['loss_usd']:,.2f} scenario loss; ${plan['audit']['accounted_loss_usd']:,.2f} accounted loss", flush=True)


if __name__ == "__main__":
    main()
