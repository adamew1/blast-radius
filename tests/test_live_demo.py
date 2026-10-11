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


if __name__ == "__main__":
    unittest.main()
