"""Numerical adversarial checks for single-event stress and liquidity protection."""
import copy
import itertools
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np

os.environ["BLAST_RADIUS_OFFLINE"] = "1"

from blast_radius.discovery.graph import DependencyGraph, Edge, Node
from blast_radius.fire_drill.execution import exit_options, load_execution
from blast_radius.fire_drill.model import Portfolio, discover, prepare, shortfall_loss, stress_book, stress_graph
from blast_radius.fire_drill.optimize import plan_rescue, verify_plan
from blast_radius.fire_drill.presentation import network
from blast_radius.portfolio.book import load_book


def graph():
    g = DependencyGraph("root")
    for nid, kind in (("root", "position"), ("a", "token"), ("b", "token"), ("issuer", "issuer")):
        g.add_node(Node(nid, kind, nid))
    g.add_edge(Edge("root", "a", "backing"))
    g.add_edge(Edge("a", "issuer", "issuer"))
    return g


def fixture():
    stress = {"loss_usd": 140.0, "positions": [
        {"id": "a", "label": "A", "loss_usd": 80, "size_usd": 100},
        {"id": "b", "label": "B", "loss_usd": 60, "size_usd": 100}]}
    def options(cost):
        return [{"fraction": f, "notional_usd": f * 100, "execution_usd": f * cost,
                 "conversion_usd": f, "carry_usd": f * 2} for f in (0, .5, 1)]
    execution = {"options": {"a": options(3), "b": options(5)},
                 "vault_caps": {"a": {"shared": 100}, "b": {"shared": 100}},
                 "resources": {"shared": 150}}
    return stress, execution


class StressTests(unittest.TestCase):
    def test_zero_shock_and_monotonic_severity(self):
        g = graph()
        values = [stress_graph(g, "issuer", f)["fraction"] for f in (0, .1, .5, 1)]
        self.assertEqual(values[0], 0)
        self.assertEqual(values, sorted(values))
        self.assertAlmostEqual(values[-1], .95 * .9)

    def test_duplicate_alternate_path_cannot_inflate_claim(self):
        g = graph()
        baseline = stress_graph(g, "issuer", 1)["fraction"]
        g.add_edge(Edge("a", "b", "backing"))
        g.add_edge(Edge("b", "issuer", "issuer"))
        self.assertAlmostEqual(stress_graph(g, "issuer", 1)["fraction"], baseline)

    def test_aggregate_shortfall_is_incremental_and_bounded(self):
        s = {"supplyAssetsUsd": 100, "borrowAssetsUsd": 80, "collateralAssetsUsd": 120}
        self.assertEqual(shortfall_loss(s, 0), 0)
        self.assertEqual(shortfall_loss(s, .2), 0)
        self.assertAlmostEqual(shortfall_loss(s, .5), .2)
        self.assertAlmostEqual(shortfall_loss(s, 1), .8)
        s["collateralAssetsUsd"] = 70
        self.assertEqual(shortfall_loss(s, 0), 0)
        with self.assertRaises(ValueError):
            shortfall_loss({}, .5)

    def test_disjoint_funded_allocations_add(self):
        # IDs deliberately match the allocation canonical IDs.
        g = DependencyGraph("root")
        for nid, kind in (("root", "position"), ("lmkt:morpho:x", "lending_market"),
                          ("lmkt:morpho:y", "lending_market"), ("collat", "token")):
            g.add_node(Node(nid, kind, nid))
        for mid in ("x", "y"):
            g.add_edge(Edge("root", f"lmkt:morpho:{mid}", "collateral", 50))
            g.add_edge(Edge(f"lmkt:morpho:{mid}", "collat", "collateral"))
        vault = {"state": {"totalAssetsUsd": 200, "allocation": [
            {"supplyAssetsUsd": 100, "market": {"marketId": mid, "state": {
                "supplyAssetsUsd": 100, "borrowAssetsUsd": 80, "collateralAssetsUsd": 120}}}
            for mid in ("x", "y")]}}
        r = stress_graph(g, "collat", 1, vault)
        self.assertAlmostEqual(r["fraction"], .8)
        root_flows = [v["root_loss_fraction"] for (u, _), v in r["flows"].items() if u == "root"]
        self.assertAlmostEqual(sum(root_flows), .8)

    def test_invalid_shocks_are_rejected(self):
        for value in (-1, 1.1, float("nan")):
            with self.assertRaises(ValueError):
                stress_graph(graph(), "issuer", value)


class OptimizerTests(unittest.TestCase):
    def test_matches_exhaustive_enumeration(self):
        s, e = fixture()
        limit = 65
        candidates = []
        for a, b in itertools.product(e["options"]["a"], e["options"]["b"]):
            if a["notional_usd"] + b["notional_usd"] > 150:
                continue
            accounted = 140 - 80*a["fraction"] - 60*b["fraction"] + sum(o["execution_usd"]+o["conversion_usd"] for o in (a,b))
            if accounted <= limit:
                candidates.append(sum(o["execution_usd"]+o["conversion_usd"]+o["carry_usd"] for o in (a,b)))
        result = plan_rescue(s, e, limit)
        self.assertEqual(result["status"], "optimal")
        self.assertTrue(result["audit"]["verified"])
        self.assertAlmostEqual(result["audit"]["protection_cost_usd"], min(candidates))

    def test_satisfied_limit_requires_no_sale(self):
        s, e = fixture()
        p = plan_rescue(s, e, 140)
        self.assertEqual(p["audit"]["capital_sold_usd"], 0)

    def test_shared_capacity_and_lock_make_target_infeasible(self):
        s, e = fixture()
        e["resources"]["shared"] = 100
        p = plan_rescue(s, e, 0)
        self.assertEqual(p["status"], "infeasible")
        self.assertFalse(p["target_met"])
        self.assertTrue(p["minimum_attainable_proved"])
        self.assertLessEqual(sum(w["amount_usd"] for w in p["withdrawals"]), 100.02)
        p = plan_rescue(s, e, 50, ["a"])
        self.assertEqual(p["status"], "infeasible")
        self.assertEqual(next(a for a in p["actions"] if a["id"]=="a")["fraction"], 0)

    def test_unavailable_option_is_never_selected(self):
        s, e = fixture()
        e["options"]["a"] = e["options"]["a"][:1]
        p = plan_rescue(s, e, 100)
        self.assertEqual(next(a for a in p["actions"] if a["id"]=="a")["fraction"], 0)

    def test_independent_audit_rejects_tampering(self):
        s, e = fixture()
        p = plan_rescue(s, e, 65)
        actions = copy.deepcopy(p["actions"])
        actions[0]["execution_usd"] = 0.123
        with self.assertRaises(ValueError):
            verify_plan(s, e, actions, p["withdrawals"], [], 65)
        withdrawals = copy.deepcopy(p["withdrawals"])
        withdrawals[0]["amount_usd"] += 100
        with self.assertRaises(ValueError):
            verify_plan(s, e, p["actions"], withdrawals, [], 65)

    def test_zero_loss_does_not_buy_protection(self):
        s, e = fixture()
        s["loss_usd"] = 0
        for r in s["positions"]:
            r["loss_usd"] = 0
        p = plan_rescue(s, e, 0)
        self.assertEqual(p["audit"]["capital_sold_usd"], 0)
        self.assertIsNone(p["audit"]["break_even_probability"])

    def test_timeout_without_incumbent_is_unresolved(self):
        s,e=fixture()
        with patch("blast_radius.fire_drill.optimize.milp",return_value=SimpleNamespace(
                status=1,x=None,message="Time limit")):
            result=plan_rescue(s,e,65)
        self.assertEqual(result["status"],"unresolved")
        self.assertFalse(result["optimal"])
        self.assertFalse(result["target_met"])

    def test_invalid_solver_incumbent_cannot_claim_feasibility(self):
        s,e=fixture()
        # A 50% exit and sufficient liquidity, but too much remaining loss.
        x=np.array([0,1,0,1,0,0,.00005,0])
        with patch("blast_radius.fire_drill.optimize.milp",return_value=SimpleNamespace(
                status=1,x=x,message="Time limit",mip_gap=None)):
            result=plan_rescue(s,e,65)
        self.assertEqual(result["status"],"verification_failed")
        self.assertFalse(result["target_met"])

    def test_valid_incumbent_does_not_claim_optimality(self):
        s,e=fixture()
        x=np.array([0,0,1,0,1,0,.0001,.00005])
        with patch("blast_radius.fire_drill.optimize.milp",return_value=SimpleNamespace(
                status=1,x=x,message="Time limit",mip_gap=.1)):
            result=plan_rescue(s,e,65)
        self.assertEqual(result["status"],"feasible_incumbent")
        self.assertFalse(result["optimal"])
        self.assertTrue(result["target_met"])


class CachedBookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.book = prepare(load_book()["positions"])

    def test_real_shared_dependency_and_ranking(self):
        d = discover(self.book)
        self.assertEqual(next(r for r in d if r["id"]=="issuer:lido")["positions"], 5)
        self.assertEqual(next(r for r in d if r["id"]=="issuer:lido")["affected_capital_usd"], 5e6)
        self.assertEqual(d, sorted(d, key=lambda r:(-r["loss_usd"],-r["positions"],r["id"])))

    def test_every_real_dependency_is_zero_at_zero_and_monotonic(self):
        for r in discover(self.book):
            values = [stress_book(self.book, r["id"], f)["loss_usd"] for f in (0,.1,.5,1)]
            self.assertEqual(values[0], 0, r["id"])
            self.assertEqual(values, sorted(values), r["id"])
            self.assertLessEqual(values[-1], 10e6)

    def test_rpc_decimals_and_quote_valuation(self):
        bundle = load_execution()
        self.assertEqual(bundle["positions"]["pt-reusd"]["input_asset"]["decimals"], 6)
        for record in bundle["positions"].values():
            for asset in (record["input_asset"], record["output_asset"]):
                self.assertEqual(asset["decimals"], int(asset["rpc_response"]["result"],16))
            for q in record["options"]:
                if q["available"]:
                    a=record["output_asset"]
                    output=int(q["amount_out"])/10**a["decimals"]*a["price_usd"]
                    self.assertAlmostEqual(output,q["output_value_usd"],places=5)
                    self.assertAlmostEqual(max(0,q["notional_usd"]-output),q["mark_shortfall_usd"],places=5)

    def test_real_rescue_reproducible_and_honest(self):
        s=stress_book(self.book,"issuer:lido")
        e=exit_options(self.book)
        a=plan_rescue(s,e,500000)
        b=plan_rescue(s,e,500000)
        self.assertEqual(a["actions"],b["actions"])
        self.assertTrue(a["target_met"])
        self.assertLessEqual(a["audit"]["accounted_loss_usd"],500000.02)
        p=plan_rescue(s,e,500000,["pt-wsteth"])
        self.assertEqual(p["status"],"infeasible")

    def test_dense_global_graph_is_summarized_without_inventing_paths(self):
        r=discover(self.book)
        s=stress_book(self.book,"chain:ethereum")
        view=network(self.book,r,s,True,True)
        self.assertEqual(len({n["id"] for n in view["nodes"]}),len(view["nodes"]))
        self.assertLessEqual(len(view["nodes"]),24)
        for e in view["edges"]:
            for record in e["evidence"]:
                if record["collapsed"]:
                    g=self.book.graphs[record["position"]]
                    for path in record["paths"]:
                        self.assertTrue(all(g.g.has_edge(u,v) for u,v in zip(path,path[1:])))


if __name__ == "__main__":
    unittest.main()
