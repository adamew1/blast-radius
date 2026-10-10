"""Regressions for financial flaws found in the final judge audit."""
import copy
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ["BLAST_RADIUS_OFFLINE"] = "1"
from blast_radius.fire_drill.execution import load_execution
from blast_radius.risk.exit_cost import exit_cost
from blast_radius.risk.decision import decide
from blast_radius.discovery.graph import DependencyGraph, Node
from blast_radius.discovery.resolvers import Context, resolve_morpho_vault
from blast_radius.fire_drill.model import stress_graph
from blast_radius.discovery.graph import Edge


class AuditRegressions(unittest.TestCase):
    def test_pt_underlying_zero_leaves_no_invented_recovery(self):
        for nested in (False, True):
            g = DependencyGraph("root")
            root = Node("root", "token" if nested else "position", "PT",
                        meta={"is_pendle_pt":True} if nested else {"pt":"observed PT address"})
            g.add_node(root)
            g.add_node(Node("underlying", "token", "underlying"))
            g.add_edge(Edge("root", "underlying", "backing"))
            for severity in (0, .2, .9, 1):
                self.assertAlmostEqual(stress_graph(g,"underlying",severity)["fraction"],severity)

    def test_research_pt_reusd_uses_six_decimal_captured_quote_and_no_extra_fee(self):
        record = load_execution()["positions"]["pt-reusd"]
        q = next(q for q in record["options"] if q["fraction"] == 1)
        result = exit_cost(record["position"])
        self.assertTrue(result["available"])
        self.assertEqual(record["input_asset"]["decimals"], 6)
        self.assertAlmostEqual(result["cost_pct"], q["mark_shortfall_usd"] / 1e6 + .0012)
        self.assertEqual(result["raw_cache_key"], q["raw_cache_key"])

    def test_unquoted_exact_size_never_receives_a_guessed_fill(self):
        p = copy.deepcopy(load_execution()["positions"]["pt-wsteth"]["position"])
        p["size_usd"] = 123456
        self.assertFalse(exit_cost(p)["available"])

    def test_morpho_bound_excludes_unfunded_market_liquidity(self):
        vault = {"state": {"allocation": [
            {"supplyAssetsUsd": 0, "market": {"state": {"liquidityAssetsUsd": 1e9}}},
            {"supplyAssetsUsd": 40, "market": {"state": {"liquidityAssetsUsd": 100}}}]}}
        with patch("blast_radius.risk.exit_cost.morpho.vault_by_address", return_value=vault):
            result = exit_cost({"kind":"morpho_vault", "vault":"x", "size_usd":50})
        self.assertEqual(result["withdrawable_usd"], 40)
        self.assertFalse(result["available"])

    def test_unavailable_execution_cannot_issue_stay_or_exit_recommendation(self):
        g = DependencyGraph("root")
        g.add_node(Node("root", "position", "root"))
        result = SimpleNamespace(el=.8, cvar95=.9)
        with patch("blast_radius.risk.decision.top_contributors", return_value=[]):
            decision = decide(g, result, {"available":False,"cost_pct":0}, .01, 1)
        self.assertEqual(decision["verdict"], "REVIEW")
        self.assertFalse(decision["exit_available"])

    def test_zero_net_apy_does_not_fall_back_to_positive_gross_apy(self):
        g = DependencyGraph("root")
        root = Node("root", "position", "root")
        g.add_node(root)
        vault = {"state":{"netApy":0.0,"apy":.1,"allocation":[]}}
        with patch("blast_radius.discovery.resolvers.morpho.vault_by_address", return_value=vault):
            resolve_morpho_vault(g, root, Context(), {"vault":"x"})
        self.assertEqual(root.meta["apy"], 0.0)


if __name__ == "__main__":
    unittest.main()
