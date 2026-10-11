"""Snapshot-only application retains the baseline and editable portfolio offline."""
from unittest.mock import patch
import unittest

from blast_radius.config import ROOT


class SnapshotUiTests(unittest.TestCase):
    def app(self, stale_mode=False):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file(str(ROOT/"app/Home.py"), default_timeout=30)
        app.query_params["fallback"] = "1"
        if stale_mode:
            app.session_state["data_mode"] = "Live Mode"
        app.run()
        self.assertFalse(app.exception)
        return app

    def button(self, app, label):
        return next(b for b in app.button if b.label == label)

    def test_removed_live_controls_and_old_session_cannot_trigger_requests(self):
        with patch("requests.Session.request", side_effect=AssertionError("Snapshot must stay offline")):
            app = self.app(stale_mode=True)
            self.assertEqual(app.metric[0].value, "$10,000,000")
            self.assertFalse(any(r.label == "Data mode" for r in app.radio))
            self.assertFalse(any("live" in b.label.lower() or "fetch" in b.label.lower() for b in app.button))
            self.assertTrue(self.button(app, "Find My Weakest Point"))

    def test_original_baseline_and_lock_infeasibility_work_without_network(self):
        with patch("requests.Session.request", side_effect=AssertionError("Snapshot must stay offline")):
            app = self.app()
            self.button(app, "Find My Weakest Point").click().run()
            self.button(app, "BUILD RESCUE PLAN").click().run()
            self.assertFalse(app.exception)
            plan = app.session_state["plan"]
            self.assertTrue(plan["audit"]["verified"])
            self.assertAlmostEqual(plan["audit"]["accounted_loss_usd"], 498_999.85, delta=.01)
            next(m for m in app.multiselect if m.label == "Lock positions").set_value(["pt-wsteth"]).run()
            self.assertIsNone(app.session_state["plan"])
            self.button(app, "BUILD RESCUE PLAN").click().run()
            self.assertEqual(app.session_state["plan"]["status"], "infeasible")
            self.assertAlmostEqual(app.session_state["plan"]["audit"]["accounted_loss_usd"], 1_004_800, delta=.01)

    def test_custom_five_position_book_recalculates_and_resets_offline(self):
        amounts = {"steakhouse-eth": 100_000, "gauntlet-usdc-prime": 150_000,
                   "hakutora-usdc": 150_000, "yearn-og-usdc": 100_000,
                   "catalog-pt-0xc5f938a8ef5f3bf9e72f5aa094baf5e03f4727d3": 500_000}
        with patch("requests.Session.request", side_effect=AssertionError("Snapshot must stay offline")):
            app = self.app()
            app.multiselect(key="catalog_selection_").set_value(list(amounts)).run()
            for pid, amount in amounts.items():
                app.number_input(key="allocation_" + pid).set_value(amount)
            self.button(app, "Apply portfolio & rediscover").click().run()
            self.assertFalse(app.exception)
            self.assertEqual({k: v for k, v in app.session_state["portfolio_sizes"].items() if v}, amounts)
            self.assertEqual(app.metric[0].value, "$1,000,000")
            self.button(app, "Find My Weakest Point").click().run()
            self.button(app, "BUILD RESCUE PLAN").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(app.session_state["plan"]["audit"]["verified"])
            self.button(app, "Restore original portfolio").click().run()
            self.assertEqual(app.metric[0].value, "$10,000,000")
            self.assertIsNone(app.session_state["portfolio_sizes"])
            self.assertIsNone(app.session_state["plan"])


if __name__ == "__main__":
    unittest.main()
