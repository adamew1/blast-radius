"""Native-unit normalization against API-shaped responses; old engine untouched."""
import copy
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests

from app.live_data import capture_live, live_receipt, save_live_receipt, verify_live_receipt
from blast_radius.fire_drill.live import analyze_live, raw
from blast_radius.sources.live import LiveInputError, ObservationClient, digest
from tests import test_live as fixtures
from tests.test_live import Api, NOW, WSTETH


class NativeLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.LiveTests.setUpClass()
        cls.fixtures = copy.deepcopy(fixtures.LiveTests.fixtures)
        vaults, _, _, assets = cls.fixtures
        for vault in vaults.values():
            loan = vault["asset"]
            loan["price"] = {"usd": 1, "timestamp": NOW}
            decimals = loan["decimals"]
            state = vault["state"]
            total = 0
            for allocation in state["allocation"]:
                allocation["supplyAssets"] = str(int(Decimal(str(allocation["supplyAssetsUsd"])) * 10 ** decimals))
                total += int(allocation["supplyAssets"])
                market = allocation["market"]
                market["loanAsset"].update(decimals=decimals, price={"usd": 1, "timestamp": NOW})
                s = market["state"]
                for native, usd in (("supplyAssets", "supplyAssetsUsd"), ("borrowAssets", "borrowAssetsUsd")):
                    s[native] = str(int(Decimal(str(s[usd])) * 10 ** decimals))
                s["liquidityAssets"] = str(int(s["supplyAssets"]) - int(s["borrowAssets"]))
                collateral = market.get("collateralAsset")
                if collateral:
                    cd = assets.get(raw(collateral["address"]), {}).get("decimals", 18)
                    collateral.update(decimals=cd, price={"usd": 1, "timestamp": NOW})
                    s["collateralAssets"] = str(int(Decimal(str(s["collateralAssetsUsd"] or 0)) * 10 ** cd))
                else:
                    s["collateralAssets"] = "0"
            state["totalAssets"] = str(total)
        cls.vault = next(p for p in fixtures.LiveTests.catalog if p["id"] == "hakutora-usdc")

    def setUp(self):
        self.api = Api(self.fixtures)
        self.now = NOW

    def capture(self, positions=None, policy=None):
        return capture_live(positions or [self.vault], client=ObservationClient(session=self.api, clock=lambda: self.now, policy=policy))

    def test_inconsistent_display_usd_is_revalued_from_consistent_native_units(self):
        for vault in self.api.vaults.values():
            vault["state"]["totalAssetsUsd"] *= 1.01
            for allocation in vault["state"]["allocation"]:
                allocation["supplyAssetsUsd"] *= 1.02
                state = allocation["market"]["state"]
                state["supplyAssetsUsd"] *= 1.03
                state["liquidityAssetsUsd"] *= .97
        run = self.capture()
        self.assertTrue(run.freshness()["execution_usable"], run.risk_error)
        report = run.client.normalization
        self.assertTrue(any(m["reported_usd"] != m["normalized_usd"] for m in report["markets"].values()))
        for market in report["markets"].values():
            s = market["normalized_usd"]
            self.assertAlmostEqual(s["supplyAssetsUsd"] - s["borrowAssetsUsd"], s["liquidityAssetsUsd"], delta=.00001)
        rec = live_receipt(run, analyze_live(run, "chain:ethereum", 1, rescue=True))
        self.assertEqual(rec["receipt_schema"], "blast-radius-native-live-v2")
        with patch("requests.Session.request", side_effect=AssertionError("offline replay")):
            replay = verify_live_receipt(rec)
        self.assertEqual(replay.client.normalization, report)
        # The captured provider response has not been overwritten by valuation.
        source = rec["observations"][0]["response"]["data"]["vaultByAddress"]["state"]
        self.assertNotEqual(source["totalAssetsUsd"], run.vault_records[raw(self.vault["vault"])]["state"]["totalAssetsUsd"])

    def test_native_inconsistency_missing_units_and_wrong_decimals_still_reject(self):
        for issue in ("liquidity", "debt", "vault total", "missing", "float", "decimals", "collateral"):
            self.api = Api(self.fixtures)
            v = self.api.vaults[raw(self.vault["vault"])]
            a = next(a for a in v["state"]["allocation"] if int(a["supplyAssets"]))
            m, s = a["market"], a["market"]["state"]
            if issue == "liquidity":
                s["liquidityAssets"] = str(int(s["liquidityAssets"]) + 100)
            elif issue == "debt":
                s["borrowAssets"] = str(int(s["supplyAssets"]) + 1)
            elif issue == "vault total":
                v["state"]["totalAssets"] = str(int(v["state"]["totalAssets"]) + 100)
            elif issue == "missing":
                s.pop("liquidityAssets")
            elif issue == "float":
                s["supplyAssets"] = float(s["supplyAssets"])
            elif issue == "decimals":
                m["loanAsset"]["decimals"] += 1
            else:
                s["collateralAssets"] = "-1"
            with self.subTest(issue=issue):
                run = self.capture()
                self.assertFalse(run.freshness()["risk_usable"], issue)
                with self.assertRaises(LiveInputError):
                    analyze_live(run, "chain:ethereum", 1, rescue=True)
                verify_live_receipt(live_receipt(run))

    def test_prices_require_timestamps_and_expire_as_material_risk_inputs(self):
        for value in (None, NOW - 901, NOW + 16):
            self.api = Api(self.fixtures)
            self.api.vaults[raw(self.vault["vault"])]["asset"]["price"]["timestamp"] = value
            with self.subTest(value=value):
                self.assertFalse(self.capture().freshness()["risk_usable"])
        self.api = Api(self.fixtures)
        self.api.vaults[raw(self.vault["vault"])]["asset"]["price"]["timestamp"] = NOW - 890
        run = self.capture()
        self.assertTrue(run.freshness()["risk_usable"])
        self.now += 11
        self.assertFalse(run.freshness()["risk_usable"])

    def test_rejected_native_price_identifies_vault_and_token_from_raw_evidence(self):
        from app.components.live import rejected_morpho_inputs
        from blast_radius.sources.live import FreshnessPolicy
        yearn = next(p for p in fixtures.LiveTests.catalog if p["id"] == "yearn-og-usdc")
        address = "0xd2af830e8cbdfed6cc11bab697bb25496ed6fa62"
        for positions in ([yearn], [fixtures.LiveTests.pt]):
            self.api = Api(self.fixtures)
            for allocation in self.api.vaults[raw(yearn["vault"])]["state"]["allocation"]:
                asset = allocation["market"].get("collateralAsset")
                if asset and raw(asset["address"]) == address:
                    asset["price"]["timestamp"] = NOW - 4738
            with self.subTest(positions=[p["id"] for p in positions]):
                run = self.capture(positions, FreshnessPolicy(risk_seconds=3600, max_skew_seconds=3600))
                self.assertFalse(run.freshness()["risk_usable"])
                self.assertNotIn(raw(yearn["vault"]), run.vault_records)
                rows = rejected_morpho_inputs(run, run.freshness())
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["identity"], address)
                self.assertEqual(rows[0]["input"], "WOUSD USD price")
                self.assertIn(yearn["label"], rows[0]["positions"])
                self.assertEqual(rows[0]["age_seconds"], 4738)
                self.assertEqual(rows[0]["max_age_seconds"], 3600)
                self.assertEqual(rows[0]["scope"], ["selected holding" if positions == [yearn]
                                                    else "PT contagion discovery"])

    def test_one_price_per_token_and_all_shared_markets_use_identical_usd_values(self):
        for i, vault in enumerate(self.api.vaults.values()):
            vault["asset"]["price"]["usd"] = 1 + i / 1000
            for a in vault["state"]["allocation"]:
                a["market"]["loanAsset"]["price"]["usd"] = 2 + i / 1000
        positions = [p for p in fixtures.LiveTests.catalog if p["id"] in ("hakutora-usdc", "gauntlet-usdc-prime")]
        run = self.capture(positions)
        self.assertTrue(run.freshness()["risk_usable"], run.risk_error)
        shared = {}
        for vault in run.vault_records.values():
            for a in vault["state"]["allocation"]:
                if not a["supplyAssetsUsd"]:
                    continue
                m = a["market"]
                if m["marketId"] in shared:
                    self.assertEqual(m, shared[m["marketId"]])
                shared[m["marketId"]] = m
        verify_live_receipt(live_receipt(run))

    def test_timeout_and_malformed_native_response_fail_without_historical_data(self):
        for issue in ("timeout", "malformed"):
            self.api = Api(self.fixtures)
            if issue == "timeout":
                def fail(*args):
                    raise requests.Timeout("native API timeout")
                self.api.fail = fail
            else:
                self.api.vaults[raw(self.vault["vault"])]["state"] = ["invalid"]
            with self.subTest(issue=issue):
                with patch("blast_radius.sources.cache._read", side_effect=AssertionError("historical substitution")):
                    run = self.capture()
                self.assertFalse(run.freshness()["risk_usable"])
                verify_live_receipt(live_receipt(run))

    def test_normalization_tampering_and_wrong_adapter_hash_rejected(self):
        rec = live_receipt(self.capture())
        for issue in ("normalization", "code"):
            modified = copy.deepcopy(rec)
            if issue == "code":
                modified["adapter_code_hashes"]["app/live_data.py"] = "bad"
            else:
                next(iter(modified["normalization"]["prices"].values()))["usd"] = 2
            modified.pop("receipt_sha256")
            modified["receipt_sha256"] = digest(modified)
            with self.subTest(issue=issue), self.assertRaises(LiveInputError):
                verify_live_receipt(modified)

    def test_pendle_keeps_exact_quote_sizes_and_two_minute_expiry(self):
        run = self.capture([fixtures.LiveTests.pt])
        self.assertTrue(run.freshness()["execution_usable"], run.freshness())
        self.assertEqual(sum(c[1].endswith("/swap") for c in self.api.calls), 4)
        self.assertEqual(len(run.vault_records), 8)
        analysis = analyze_live(run, WSTETH, 1, loss_limit=300_000, rescue=True)
        self.assertEqual(len(analysis["exit_candidates"]["options"]["pt-wsteth"]), 5)
        self.assertTrue(analysis["plan"]["audit"]["verified"])
        verify_live_receipt(live_receipt(run, analysis))
        self.now += 121
        self.assertTrue(run.freshness()["risk_usable"])
        self.assertFalse(run.freshness()["execution_usable"])

    def test_live_button_uses_native_adapter_and_exports_replayable_receipt(self):
        from blast_radius.config import ROOT
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as directory:
            with patch("app.components.live.ObservationClient", side_effect=lambda **kw: ObservationClient(
                    session=self.api, clock=lambda: self.now, **kw)), patch(
                    "app.components.live.save_live_receipt", side_effect=lambda rec: save_live_receipt(
                        rec, Path(directory)/"artifacts/live")):
                app = AppTest.from_file(str(ROOT/"app/Home.py"), default_timeout=20).run()
                app.radio(key="data_mode").set_value("Live Mode").run()
                app.button(key="live_example").click().run()
                app.button(key="live_refresh").click().run()
                self.assertFalse(app.exception)
                self.assertFalse(app.error)
                rec = app.session_state["live_download_receipt"]
                self.assertEqual(rec["receipt_schema"], "blast-radius-native-live-v2")
                self.assertTrue(rec["analysis"]["freshness"]["risk_usable"])
                verify_live_receipt(rec)


if __name__ == "__main__":
    unittest.main()
