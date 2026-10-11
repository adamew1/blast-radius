"""Admission and financial invariants for instruments outside the prepared book."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ["BLAST_RADIUS_OFFLINE"] = "1"
from blast_radius.fire_drill.catalog import load_catalog, execution_for
from blast_radius.fire_drill.challenge import resize_positions
from blast_radius.fire_drill.evidence import receipt, source_manifest
from blast_radius.fire_drill.execution import exit_options, load_execution
from blast_radius.fire_drill.model import prepare, discover, stress_book
from blast_radius.fire_drill.optimize import plan_rescue
from blast_radius.portfolio.book import load_book
from scripts.verify_receipt import verify


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = load_book()["positions"]
        cls.catalog = load_catalog()
        cls.extra = cls.catalog[len(cls.original):]
        cls.book = prepare(cls.extra)

    def test_bounded_catalog_has_distinct_observed_instruments(self):
        self.assertEqual(self.catalog[:10], self.original)
        self.assertEqual(len(self.extra), 4)
        self.assertEqual(sum(p["kind"] == "pendle_pt" for p in self.extra), 2)
        self.assertEqual(sum(p["kind"] == "morpho_vault" for p in self.extra), 2)
        self.assertEqual(len({p.get("market", p.get("vault")).lower() for p in self.catalog}), 14)
        for p in self.extra:
            self.assertGreater(len(self.book.graphs[p["id"]].nodes()), 1)

    def test_arbitrary_addresses_and_oversized_membership_are_rejected(self):
        sizes = {p["id"]: 500_000 for p in self.catalog}
        with self.assertRaises(ValueError):
            resize_positions(self.catalog, sizes)
        sizes["arbitrary-wallet-address"] = 500_000
        with self.assertRaises(ValueError):
            resize_positions(self.catalog, sizes)

    def test_new_quotes_are_instrument_specific_and_never_extrapolated(self):
        bundle = execution_for(self.extra)
        sizes = {p["id"]: 2_000_000 if p in self.extra else 0 for p in self.catalog}
        book = prepare(resize_positions(self.catalog, sizes))
        execution = exit_options(book, bundle)
        for p in self.extra:
            if p["kind"] != "pendle_pt":
                continue
            candidates = execution["options"][p["id"]][1:]
            self.assertEqual(len(candidates), 20)
            self.assertEqual(max(o["fraction"] for o in candidates), .5)
            for option, quote in zip(candidates, bundle["positions"][p["id"]]["options"]):
                self.assertEqual(option["notional_usd"], quote["notional_usd"])
                self.assertEqual(option["execution_usd"], quote["mark_shortfall_usd"] + quote["notional_usd"]*.0002)
                self.assertEqual(option["source"], quote["raw_cache_key"])
            missing = exit_options(book, load_execution())["options"][p["id"]]
            self.assertEqual(len(missing), 1)

    def test_new_instruments_use_their_own_carry_and_funded_balance_sheets(self):
        for p in self.extra:
            graph = self.book.graphs[p["id"]]
            if p["kind"] == "morpho_vault":
                vault = self.book.vaults[p["id"]]
                self.assertEqual(vault["address"].lower(), p["vault"].lower())
                self.assertEqual(graph.node(graph.root_id).meta["apy"], vault["state"]["netApy"])
            else:
                record = execution_for(self.extra)["positions"][p["id"]]
                self.assertEqual(record["position"], p)
            options = exit_options(self.book, execution_for(self.extra))["options"][p["id"]]
            for option in options:
                self.assertAlmostEqual(option["carry_usd"], option["notional_usd"]*max(0, graph.node(graph.root_id).meta["apy"])*30/365)

    def test_discovery_and_stress_recompute_for_an_entirely_new_book(self):
        ranking = discover(self.book)
        for r in ranking:
            losses = [stress_book(self.book, r["id"], f)["loss_usd"] for f in (0, .5, 1)]
            self.assertEqual(losses[0], 0)
            self.assertEqual(losses, sorted(losses))
            self.assertLessEqual(losses[-1], 4e6)
        for p in self.extra:
            if p["kind"] == "pendle_pt":
                from blast_radius.sources import pendle
                market = next(m for m in pendle.markets_active()["markets"] if m["address"].lower() == p["market"])
                target = "token:ethereum:" + market["underlyingAsset"].split("-", 1)[-1]
                stress = stress_book(self.book, target)
                row = next(r for r in stress["positions"] if r["id"] == p["id"])
                self.assertEqual(row["fraction"], 1)

    def test_catalog_receipt_reproduces_and_rejects_unadmitted_instrument(self):
        target = "token:ethereum:0x38eeb52f0771140d10c4e9a9a72349a329fe8a6a"
        bundle = execution_for(self.extra)
        stress, execution = stress_book(self.book, target), exit_options(self.book, bundle)
        plan = plan_rescue(stress, execution, 200_000)
        self.assertTrue(plan["target_met"])
        rec = receipt(stress, execution, plan, source_manifest(), bundle, positions=self.extra, catalog_mode=True)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(rec), encoding="utf-8")
            verify(path)
            changed = copy.deepcopy(rec)
            changed["portfolio"][0]["market"] = self.original[0]["market"]
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(ValueError):
                verify(path)

    def test_default_bundle_and_default_portfolio_are_preserved(self):
        self.assertEqual(execution_for(self.original), load_execution())
        self.assertEqual(len(load_execution()["positions"]), 4)
        book = prepare(self.original)
        stress = stress_book(book, "token:ethereum:0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0")
        plan = plan_rescue(stress, exit_options(book), 500_000)
        self.assertAlmostEqual(plan["audit"]["accounted_loss_usd"], 498999.85, delta=.01)


if __name__ == "__main__":
    unittest.main()
