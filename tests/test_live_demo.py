"""Demo recovery uses genuine saved observations and preserves their identity."""
import tempfile
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

from app.live_data import save_live_receipt, verify_live_receipt
from blast_radius.config import ROOT
from blast_radius.sources.live import LiveInputError
from blast_radius.sources.live import digest


class LiveDemoTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file(str(ROOT/"app/Home.py"), default_timeout=30)
        app.query_params["fallback"] = "1"
        app.run()
        app.radio(key="data_mode").set_value("Live Mode").run()
        return app

    def test_saved_replay_completes_rescue_offline_and_receipt_never_claims_current_data(self):
        with tempfile.TemporaryDirectory() as directory, patch(
                "requests.Session.request", side_effect=AssertionError("replay must be offline")), patch(
                "app.components.live.save_live_receipt", side_effect=lambda rec: save_live_receipt(rec, Path(directory))):
            app = self.app()
            app.button(key="live_saved").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("HISTORICAL REPLAY" in w.value for w in app.warning))
            self.assertEqual(app.multiselect(key="live_selected").value, ["hakutora-usdc"])
            app.button(key="live_rescue").click().run()
            self.assertFalse(app.exception)
            rec = app.session_state["live_download_receipt"]
            self.assertFalse(rec["presentation_context"]["fresh_at_replay"])
            self.assertIn("not current live data", rec["classification"])
            self.assertEqual(rec["analysis"]["plan"]["actions"][0]["fraction"], .45)
            verify_live_receipt(rec)
            from scripts.verify_receipt import verify
            verify(save_live_receipt(rec, Path(directory)))
            tampered = copy.deepcopy(rec)
            tampered["presentation_context"]["fresh_at_replay"] = True
            tampered.pop("receipt_sha256")
            tampered["receipt_sha256"] = digest(tampered)
            with self.assertRaisesRegex(ValueError, "replay context"):
                verify(save_live_receipt(tampered, Path(directory)))
            app.multiselect(key="live_locks").set_value(["hakutora-usdc"]).run()
            self.assertNotIn("live_analysis", app.session_state)
            app.button(key="live_rescue").click().run()
            self.assertEqual(app.session_state["live_analysis"]["plan"]["status"], "infeasible")

    def test_demo_api_failure_recovers_with_labelled_replay_without_network(self):
        with tempfile.TemporaryDirectory() as directory, patch(
                "requests.Session.request", side_effect=AssertionError("unexpected network")), patch(
                "app.components.live.capture_live", side_effect=LiveInputError("Provider unavailable")), patch(
                "app.components.live.save_live_receipt", side_effect=lambda rec: save_live_receipt(rec, Path(directory))):
            app = self.app()
            app.button(key="live_start").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("HISTORICAL REPLAY" in w.value for w in app.warning))
            self.assertEqual(app.session_state["live_fetch_issue"], "Provider unavailable")
            app.button(key="live_rescue").click().run()
            self.assertTrue(app.session_state["live_analysis"]["plan"]["audit"]["verified"])
            self.assertFalse(app.session_state["live_download_receipt"]["presentation_context"]["fresh_at_replay"])

    def test_partial_severity_action_preserves_25_percent_and_clears_previous_plan(self):
        from app.components.live_workspace import apply_action, revision
        from streamlit.testing.v1 import AppTest
        # Execute the real handler inside a Streamlit context, with offline data.
        source = '''
from app.components.live_workspace import replay_saved, apply_action, revision
import streamlit as st
replay_saved()
run = st.session_state.live_run
apply_action({"type":"severity", "value":.25, "nonce":1, "revision":revision(run)})
st.write(st.session_state.live_severity)
'''
        with patch("requests.Session.request", side_effect=AssertionError("offline")):
            app = AppTest.from_string(source, default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["live_severity"], 25)
            self.assertNotIn("live_analysis", app.session_state)

    def test_allocation_error_names_the_field_and_clears_the_previous_plan(self):
        with tempfile.TemporaryDirectory() as directory, patch(
                "requests.Session.request", side_effect=AssertionError("must stay offline")), patch(
                "app.components.live.save_live_receipt", side_effect=lambda rec: save_live_receipt(rec, Path(directory))):
            app = self.app()
            app.button(key="live_saved").click().run()
            app.button(key="live_rescue").click().run()
            self.assertIn("live_analysis", app.session_state)
            app.number_input(key="live_size_hakutora-usdc").set_value(120_000).run()
            self.assertFalse(app.exception)
            self.assertNotIn("live_analysis", app.session_state)
            error = " ".join(e.value for e in app.error)
            for expected in ("Hakutora", "$120,000", "$100,000", "$150,000"):
                self.assertIn(expected, error)
            self.assertEqual(app.number_input(key="live_size_hakutora-usdc").value, 120_000)
            app.number_input(key="live_size_hakutora-usdc").set_value(150_000).run()
            self.assertFalse(any("supported demo allocation" in e.value for e in app.error))

    def test_frozen_recovery_keeps_the_user_portfolio_and_completes_offline(self):
        amounts = {"steakhouse-eth": 100_000, "gauntlet-usdc-prime": 150_000,
                   "hakutora-usdc": 150_000, "yearn-og-usdc": 100_000,
                   "catalog-pt-0xc5f938a8ef5f3bf9e72f5aa094baf5e03f4727d3": 500_000}
        with patch("requests.Session.request", side_effect=AssertionError("Snapshot must stay offline")):
            app = self.app()
            app.multiselect(key="live_selected").set_value(list(amounts)).run()
            for pid, amount in amounts.items():
                app.number_input(key="live_size_" + pid).set_value(amount).run()
            app.session_state["plan"] = {"stale": True}
            app.session_state["baseline"] = {"stale": True}
            app.button(key="live_snapshot_portfolio").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.radio(key="data_mode").value, "Snapshot Mode")
            self.assertEqual({k: v for k, v in app.session_state["portfolio_sizes"].items() if v}, amounts)
            self.assertIsNone(app.session_state["plan"])
            self.assertIsNone(app.session_state["baseline"])
            self.assertEqual(app.metric[0].value, "$1,000,000")
            next(b for b in app.button if b.label == "Find My Weakest Point").click().run()
            next(b for b in app.button if b.label == "BUILD RESCUE PLAN").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(app.session_state["plan"]["audit"]["verified"])


if __name__ == "__main__":
    unittest.main()
