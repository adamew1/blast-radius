"""Financial invariants for judge-modified allocations to frozen instruments."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ["BLAST_RADIUS_OFFLINE"] = "1"
from blast_radius.fire_drill.challenge import resize_positions
from blast_radius.fire_drill.evidence import receipt, source_manifest
from blast_radius.fire_drill.execution import exit_options, load_execution
from blast_radius.fire_drill.model import discover, prepare, stress_book
from blast_radius.fire_drill.optimize import plan_rescue
from blast_radius.fire_drill.presentation import network
from blast_radius.portfolio.book import load_book
from scripts.verify_receipt import verify

WSTETH = "token:ethereum:0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0"


class PortfolioChallengeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.supported = load_book()["positions"]
        cls.bundle = load_execution()
        cls.original = prepare(cls.supported)

    def sizes(self, **changes):
        return {p["id"]: changes.get(p["id"], p["size_usd"]) for p in self.supported}

    def test_invalid_allocations_fail_without_mutating_supported_book(self):
        original = copy.deepcopy(self.supported)
        for size in (-50_000, 2_050_000, 123456, float("nan"), float("inf"), True, "500000"):
            with self.subTest(size=size), self.assertRaises(ValueError):
                resize_positions(self.supported, self.sizes(**{"pt-wsteth": size}))
        for sizes in ({}, {"unknown": 1e6}, {p["id"]: 0 for p in self.supported}):
            with self.assertRaises(ValueError):
                resize_positions(self.supported, sizes)
        self.assertEqual(self.supported, original)

    def test_resizing_uses_exact_captured_amounts_without_scaled_costs(self):
        for size in (50_000, 750_000, 1_250_000, 2_000_000):
            with self.subTest(size=size):
                book = prepare(resize_positions(self.supported, self.sizes(**{"pt-wsteth": size})))
                actual = exit_options(book, self.bundle)["options"]["pt-wsteth"][1:]
                quotes = [q for q in self.bundle["positions"]["pt-wsteth"]["options"]
                          if q["available"] and q["notional_usd"] <= size]
                self.assertEqual(len(actual), len(quotes))
                for option, quote in zip(actual, quotes):
                    self.assertEqual(option["notional_usd"], quote["notional_usd"])
                    self.assertEqual(option["source"], quote["raw_cache_key"])
                    self.assertEqual(option["execution_usd"], quote["mark_shortfall_usd"] + quote["notional_usd"] * .0002)
                    self.assertAlmostEqual(option["fraction"] * size, quote["notional_usd"])
                self.assertLessEqual(max(o["notional_usd"] for o in actual), min(size, 1e6))

    def test_missing_quote_and_changed_instrument_cannot_borrow_a_fill(self):
        book = prepare(resize_positions(self.supported, self.sizes(**{"pt-wsteth": 750_000})))
        bundle = copy.deepcopy(self.bundle)
        bundle["positions"]["pt-wsteth"]["options"][0]["available"] = False
        self.assertNotIn(50_000, [o["notional_usd"] for o in exit_options(book, bundle)["options"]["pt-wsteth"]])
        book.positions = copy.deepcopy(book.positions)
        next(p for p in book.positions if p["id"] == "pt-wsteth")["market"] = "unsupported"
        self.assertEqual(len(exit_options(book)["options"]["pt-wsteth"]), 1)

    def test_removal_and_resize_recompute_discovery_loss_and_presentation(self):
        sizes = self.sizes(**{"pt-wsteth": 0, "steakhouse-eth": 500_000})
        book = prepare(resize_positions(self.supported, sizes))
        stress = stress_book(book, "issuer:lido")
        original = stress_book(self.original, "issuer:lido")
        removed = next(r["loss_usd"] for r in original["positions"] if r["id"] == "pt-wsteth")
        resized = next(r["loss_usd"] for r in original["positions"] if r["id"] == "steakhouse-eth")
        self.assertAlmostEqual(stress["loss_usd"], original["loss_usd"] - removed - resized / 2)
        ranking = discover(book)
        lido = next(r for r in ranking if r["id"] == "issuer:lido")
        self.assertEqual(lido["positions"], 4)
        self.assertEqual(lido["affected_capital_usd"], 3_500_000)
        self.assertEqual(stress["aum_usd"], 8_500_000)
        self.assertNotIn("pt-wsteth", exit_options(book)["options"])
        view = network(book, ranking, stress, True, True)
        self.assertNotIn("pos:pt-wsteth", {n["id"] for n in view["nodes"]})

    def test_larger_holding_cannot_extrapolate_its_way_to_feasibility(self):
        sizes = {p["id"]: 2_000_000 if p["id"] == "pt-wsteth" else 0 for p in self.supported}
        book = prepare(resize_positions(self.supported, sizes))
        stress, execution = stress_book(book, WSTETH), exit_options(book)
        plan = plan_rescue(stress, execution, 500_000)
        self.assertEqual(plan["status"], "infeasible")
        self.assertTrue(plan["minimum_attainable_proved"])
        self.assertEqual(plan["audit"]["capital_sold_usd"], 1_000_000)
        self.assertGreaterEqual(plan["audit"]["residual_loss_usd"], 1_000_000)

    def test_single_position_discovery_and_zero_stress(self):
        sizes = {p["id"]: 500_000 if p["id"] == "pt-susde" else 0 for p in self.supported}
        book = prepare(resize_positions(self.supported, sizes))
        ranking = discover(book)
        self.assertTrue(ranking)
        self.assertFalse(any(r["positions"] > 1 for r in ranking))
        stress = stress_book(book, ranking[0]["id"], 0)
        plan = plan_rescue(stress, exit_options(book), 0)
        self.assertEqual(plan["audit"]["capital_sold_usd"], 0)
        self.assertEqual(stress["loss_usd"], 0)

    def test_resized_vaults_keep_snapshot_claims_and_shared_resources(self):
        book = prepare(resize_positions(self.supported, self.sizes(**{"steakhouse-eth": 2_000_000})))
        original, execution = exit_options(self.original), exit_options(book)
        self.assertEqual(execution["resources"], original["resources"])
        self.assertEqual(execution["vault_caps"], original["vault_caps"])
        # A real modified book with deliberately scarce capacity cannot overspend it.
        execution["resources"] = {mid: min(10_000, cap) for mid, cap in execution["resources"].items()}
        plan = plan_rescue(stress_book(book, "issuer:lido"), execution, 0)
        self.assertEqual(plan["status"], "infeasible")
        for use in plan["audit"]["market_use"]:
            self.assertLessEqual(use["used_usd"], use["capacity_usd"] + .02)

    def test_modified_receipt_reproduces_and_rejects_identity_and_quote_tampering(self):
        book = prepare(resize_positions(self.supported, self.sizes(**{"pt-wsteth": 750_000, "steakhouse-eth": 0})))
        stress, execution = stress_book(book, "issuer:lido"), exit_options(book)
        plan = plan_rescue(stress, execution, 500_000)
        rec = receipt(stress, execution, plan, source_manifest(), self.bundle, positions=book.positions)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decision.json"
            path.write_text(json.dumps(rec), encoding="utf-8")
            verify(path)
            altered = copy.deepcopy(rec)
            altered["scenario"]["aum_usd"] += 50_000
            path.write_text(json.dumps(altered), encoding="utf-8")
            with self.assertRaises(ValueError):
                verify(path)
            altered = copy.deepcopy(rec)
            altered["portfolio"][0]["market"] = "changed"
            path.write_text(json.dumps(altered), encoding="utf-8")
            with self.assertRaises(ValueError):
                verify(path)
            altered = copy.deepcopy(rec)
            altered["quote_bundle"]["positions"]["pt-wsteth"]["options"][0]["mark_shortfall_usd"] = 0
            path.write_text(json.dumps(altered), encoding="utf-8")
            with self.assertRaises(ValueError):
                verify(path)

    def test_original_headlines_are_unchanged(self):
        plan = plan_rescue(stress_book(self.original, WSTETH), exit_options(self.original), 500_000)
        self.assertEqual(plan["status"], "optimal")
        audit = plan["audit"]
        self.assertAlmostEqual(audit["accounted_loss_usd"], 498999.85, delta=.01)
        self.assertAlmostEqual(audit["protection_cost_usd"], 22370.05, delta=.01)
        self.assertAlmostEqual(audit["capital_released_usd"], 2682047.49, delta=.01)


if __name__ == "__main__":
    unittest.main()
