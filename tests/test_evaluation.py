"""Regression checks for scoring and data handling that can otherwise inflate a pitch."""
import unittest
from unittest.mock import patch

from blast_radius.backtest.library import events
from blast_radius.backtest.prices import _nearest, _raw_series, forward_fill
from blast_radius.backtest.runner import run_event
from blast_radius.discovery.graph import DependencyGraph, Edge, Node
from blast_radius.risk.propagate import _dominant_transmission
from scripts.run_backtest import _summarise


class EvaluationTests(unittest.TestCase):
    def test_observation_is_not_available_early(self):
        raw = {"coins": {"test": {"prices": [{"timestamp": 14401, "price": .8}]}}}
        with patch("blast_radius.backtest.prices.defillama.chart", return_value=raw):
            self.assertEqual(_raw_series("test", 0, 3, "4h"), {28800: .8})

    def test_denominator_never_uses_future_price(self):
        self.assertIsNone(_nearest({14400: 100}, 0, 14400))
        self.assertEqual(_nearest({0: 100, 28800: 200}, 14400, 14400), 100)

    def test_missing_month_is_not_forward_filled_as_calm(self):
        self.assertNotIn(30*86400, forward_fill({0: 1}, [0, 30*86400]))

    def test_same_bar_exit_is_a_miss(self):
        win = dict(ts=[14400, 28800], up={14400: .8, 28800: .7},
                   dn={14400: .9, 28800: .8}, up_ref=1, dn_ref=1,
                   event_ts=0, period="4h", sec=14400)
        with patch("blast_radius.backtest.runner.event_window", return_value=win):
            result = run_event(events()[0])
        self.assertFalse(result["hit"])
        self.assertTrue(result["simultaneous"])
        self.assertEqual(result["saved_vs_naive_usd"], 0)

    def test_no_exit_penalizes_aggregate_savings(self):
        # MIM's weak liquidity transmission does not clear the fixed 1% exit cost.
        win = dict(ts=[14400, 28800], up={14400: 1, 28800: 1},
                   dn={14400: .94, 28800: .8}, up_ref=1, dn_ref=1,
                   event_ts=0, period="4h", sec=14400)
        with patch("blast_radius.backtest.runner.event_window", return_value=win):
            result = run_event(next(e for e in events() if e["id"] == "usdc_svb_mim"))
        self.assertIsNone(result["signal_ts"])
        self.assertLess(result["saved_vs_naive_usd"], 0)
        self.assertEqual(_summarise([result])["total_saved_vs_naive_usd"], result["saved_vs_naive_usd"])

    def test_shared_issuer_uses_one_dominant_path(self):
        g = DependencyGraph("root")
        for name, kind in (("root", "position"), ("a", "token"), ("b", "token"), ("issuer", "issuer")):
            g.add_node(Node(name, kind, name))
        for u, v, share, typ in (("root", "a", 100, "backing"), ("root", "b", 50, "backing"),
                                  ("a", "issuer", 100, "issuer"), ("b", "issuer", 100, "issuer")):
            g.add_edge(Edge(u, v, typ, share))
        self.assertAlmostEqual(_dominant_transmission(g)["issuer"], .95 * .9)


if __name__ == "__main__":
    unittest.main()
