"""API-boundary integration tests: current observations never borrow cache fills."""
from __future__ import annotations

import copy
from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests

os.environ["BLAST_RADIUS_OFFLINE"] = "1"

from blast_radius.config import ROOT, manual_map
from blast_radius.fire_drill.catalog import execution_for, load_catalog
from blast_radius.fire_drill.live import (RPC, analyze_live, capture_live, live_candidates,
                                          live_receipt, raw, save_live_receipt, verify_live_receipt)
from blast_radius.fire_drill.model import discover, prepare, stress_book
from blast_radius.fire_drill.execution import exit_options
from blast_radius.fire_drill.optimize import plan_rescue
from blast_radius.portfolio.book import load_book
from blast_radius.sources import morpho, pendle
from blast_radius.sources.live import FreshnessPolicy, LiveInputError, ObservationClient, digest, utc

NOW = 1791688000.0
WSTETH = "token:ethereum:0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0"


class Response:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status
        self.headers = {"Date": "fixture", "X-RateLimit-Remaining": "100"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return copy.deepcopy(self.data)


class Api:
    """Recorded protocol response shapes, with explicitly mocked current values."""
    def __init__(self, fixtures):
        self.vaults, self.active, self.markets, self.assets = copy.deepcopy(fixtures)
        self.calls = []
        self.fail = None

    def request(self, method, url, *, params, json, timeout):
        self.calls.append((method, url, params, json, timeout))
        if self.fail:
            response = self.fail(method, url, params, json)
            if response is not None:
                return response
        if url == morpho.URL:
            if "address" not in json["variables"]:
                by_id = {}
                for v in self.vaults.values():
                    for a in v["state"]["allocation"]:
                        by_id.setdefault(a["market"]["marketId"], a["market"])
                return Response({"data": {key: by_id[mid] for key, mid in json["variables"].items()}})
            return Response({"data": {"vaultByAddress": self.vaults[raw(json["variables"]["address"])]}})
        if url == RPC:
            if json["method"] == "eth_getBlockByNumber":
                return Response({"result": {"number": "0x123456", "timestamp": hex(int(NOW))}})
            return Response({"result": hex(self.assets[raw(json["params"][0]["to"])]["decimals"])})
        if url.endswith("/markets/active"):
            return Response(self.active)
        if url.endswith("/data"):
            return Response(self.markets[url.split("/")[-2].lower()])
        if "/assets/" in url:
            return Response(self.assets[url.split("/")[-1].lower()])
        if url.endswith("/swap"):
            inp, out = self.assets[params["tokenIn"]], self.assets[params["tokenOut"]]
            value = Decimal(params["amountIn"]) / 10 ** inp["decimals"] * Decimal(str(inp["price"]["usd"]))
            amount = int(value * Decimal(".99") / Decimal(str(out["price"]["usd"])) * 10 ** out["decimals"])
            return Response({"data": {"amountOut": str(amount), "amountIn": params["amountIn"],
                                      "tokenIn": params["tokenIn"], "tokenOut": params["tokenOut"]}})
        raise AssertionError("Unexpected endpoint " + url)


class LiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()
        cls.pt = next(p for p in cls.catalog if p["id"] == "pt-wsteth")
        vaults, shared = {}, {}
        for p in cls.catalog:
            if p["kind"] != "morpho_vault":
                continue
            v = copy.deepcopy(morpho.vault_by_address(p["vault"]))
            v["state"].update(timestamp=NOW, blockNumber=123456)
            for a in v["state"]["allocation"]:
                m = a["market"]
                m["state"].update(timestamp=NOW, blockNumber=123456, supplyApy=.03, borrowApy=.04)
                # Independently captured snapshots are made consistent in this mock.
                if m["marketId"] in shared:
                    a["market"] = copy.deepcopy(shared[m["marketId"]])
                else:
                    shared[m["marketId"]] = copy.deepcopy(m)
            vaults[raw(p["vault"])] = v
        active = copy.deepcopy(pendle.markets_active())
        markets = {raw(m["address"]): {"timestamp": utc(NOW), "impliedApy": .04,
                                        "liquidity": {"usd": 5_000_000}} for m in active["markets"]}
        assets = {}
        for record in execution_for(cls.catalog)["positions"].values():
            for a in (record["input_asset"], record["output_asset"]):
                assets[raw(a["address"])] = {"address": raw(a["address"]), "chainId": 1,
                    "symbol": a["symbol"], "decimals": a["decimals"],
                    "price": {"usd": a["price_usd"]}, "priceUpdatedAt": utc(NOW)}
        cls.fixtures = (vaults, active, markets, assets)

    def setUp(self):
        self.api = Api(self.fixtures)
        self.now = NOW

    def capture(self, positions=None, *, steps=(5, 10, 15, 20), mappings=None, policy=None):
        client = ObservationClient(session=self.api, clock=lambda: self.now, policy=policy)
        return capture_live(positions or [self.pt], client=client, quote_steps=steps, mappings=mappings)

    def test_discover_attack_collapse_rescue_prove_from_mocked_apis(self):
        # Prevent *any* accidental route into the historical API cache.
        with patch("blast_radius.sources.cache._read", side_effect=AssertionError("historical cache read")):
            run = self.capture()
            self.assertIsNone(run.risk_error)
            self.assertTrue(run.freshness()["execution_usable"], run.freshness())
            self.assertTrue(discover(run.book))
            analysis = analyze_live(run, WSTETH, 1, loss_limit=300_000, rescue=True)
            self.assertEqual(analysis["scenario"]["loss_usd"], 1_000_000)
            self.assertTrue(analysis["plan"]["target_met"])
            self.assertFalse(analysis["plan"]["executable"])
            self.assertEqual(run.book.graphs[self.pt["id"]].node("pos:" + self.pt["id"]).meta["apy"], .04)
            rec = live_receipt(run, analysis)
            with patch("requests.Session.request", side_effect=AssertionError("replay network call")):
                replay = verify_live_receipt(rec)
            self.assertEqual(stress_book(replay.book, WSTETH), analysis["scenario"])
        self.assertEqual(sum(c[1].endswith("/swap") for c in self.api.calls), 4)
        self.assertEqual(len(run.vault_records), 8)
        self.assertEqual(run.mappings, manual_map())
        self.assertFalse(run.freshness()["fully_live"])

    def test_new_quote_notional_output_and_decimals_are_exact(self):
        pt = next(p for p in self.catalog if p["id"] == "pt-reusd")
        run = self.capture([pt], steps=(1, 20))
        record = run.bundle["positions"][pt["id"]]
        self.assertEqual(record["input_asset"]["decimals"], 6)
        candidates = live_candidates(run)["options"][pt["id"]][1:]
        self.assertEqual(len(candidates), 2)
        for q, candidate in zip(record["options"], candidates):
            inp, out = record["input_asset"], record["output_asset"]
            marked = float(Decimal(q["amount_in"]) / 10 ** inp["decimals"] * Decimal(str(inp["price_usd"])))
            value = float(Decimal(q["amount_out"]) / 10 ** out["decimals"] * Decimal(str(out["price_usd"])))
            self.assertEqual(candidate["notional_usd"], marked)
            self.assertEqual(candidate["execution_usd"], max(0, marked-value)+marked*.0002)
            self.assertEqual(candidate["fraction"], marked/pt["size_usd"])

    def test_liquidity_and_balance_sheet_changes_rebuild_losses_and_bounds(self):
        p = next(p for p in self.catalog if p["id"] == "steakhouse-eth")
        run = self.capture([p])
        self.assertIsNone(run.risk_error)
        before = stress_book(run.book, WSTETH)["loss_usd"]
        # Adjust every copy of shared wstETH markets consistently.
        for v in self.api.vaults.values():
            for a in v["state"]["allocation"]:
                m = a["market"]
                if (m.get("collateralAsset") or {}).get("address", "").lower() == WSTETH.split(":")[-1]:
                    m["state"]["borrowAssetsUsd"] *= .5
                    m["state"]["liquidityAssetsUsd"] = m["state"]["supplyAssetsUsd"]-m["state"]["borrowAssetsUsd"]
        changed = self.capture([p])
        self.assertIsNone(changed.risk_error)
        self.assertLess(stress_book(changed.book, WSTETH)["loss_usd"], before)
        e = live_candidates(changed)
        for mid, cap in e["vault_caps"][p["id"]].items():
            a = next(a for a in changed.book.vaults[p["id"]]["state"]["allocation"] if a["market"]["marketId"] == mid)
            self.assertEqual(cap, min(a["supplyAssetsUsd"], a["market"]["state"]["liquidityAssetsUsd"]))
        analysis = analyze_live(changed, WSTETH, 1, loss_limit=100_000, rescue=True)
        self.assertTrue(analysis["plan"]["audit"]["verified"])

    def test_quote_failure_keeps_risk_only_and_no_plan(self):
        self.api.fail = lambda method, url, params, body: Response({}, 503) if url.endswith("/swap") else None
        run = self.capture()
        self.assertTrue(run.freshness()["risk_usable"])
        self.assertFalse(run.freshness()["execution_usable"])
        self.assertIsNone(analyze_live(run, WSTETH, 1)["plan"])
        with self.assertRaises(LiveInputError):
            analyze_live(run, WSTETH, 1, rescue=True)
        verify_live_receipt(live_receipt(run, analyze_live(run, WSTETH, 1)))

    def test_partial_quote_failure_never_infers_missing_size(self):
        counter = 0
        def fail(method, url, params, body):
            nonlocal counter
            if url.endswith("/swap"):
                counter += 1
                if counter == 2:
                    return Response({}, 404)
        self.api.fail = fail
        run = self.capture()
        options = live_candidates(run)["options"][self.pt["id"]]
        self.assertEqual(len(options), 4)  # hold plus exactly three captured quotes
        self.assertFalse(any(abs(q["fraction"]-.5) < 1e-6 for q in options))

    def test_timeout_graphql_error_http_error_and_invalid_json_reject_risk(self):
        def timeout(*args):
            raise requests.Timeout("mock deadline")
        for fail in (timeout, lambda *args: Response({}, 503),
                     lambda *args: Response({"data": {}, "errors": [{"message": "indexer unavailable"}]}),
                     lambda *args: Response({"bad": float("nan")})):
            with self.subTest(fail=fail):
                self.api.fail = fail
                run = self.capture()
                self.assertFalse(run.freshness()["risk_usable"])
                self.assertIsNone(run.book)
                self.assertTrue(run.client.observations[0].get("error"))
                with self.assertRaises(LiveInputError):
                    analyze_live(run, WSTETH, 1)

    def test_quote_timeout_and_rpc_failure_cannot_issue_plan(self):
        def fail(method, url, params, body):
            if url.endswith("/swap"):
                raise requests.Timeout("mock quote timeout")
        self.api.fail = fail
        self.assertFalse(self.capture().freshness()["execution_usable"])
        self.api.fail = lambda method, url, params, body: Response({"error": {"code": -1}}) if url == RPC else None
        run = self.capture()
        self.assertTrue(run.freshness()["risk_usable"])
        self.assertFalse(run.freshness()["execution_usable"])

    def test_rate_limit_stops_further_network_requests_and_records_failures(self):
        self.api.fail = lambda method, url, params, body: Response({}, 429) if url.endswith("/swap") else None
        run = self.capture()
        self.assertEqual(sum(c[1].endswith("/swap") for c in self.api.calls), 1)
        self.assertFalse(run.freshness()["execution_usable"])
        self.assertTrue(any("Rate limited" in r.get("error", "") for r in run.client.observations))

    def test_stale_or_missing_provider_times_cannot_use_retrieval_time(self):
        for value in (None, NOW-901, NOW+60):
            with self.subTest(value=value):
                self.api = Api(self.fixtures)
                next(iter(self.api.vaults.values()))["state"]["timestamp"] = value
                run = self.capture()
                self.assertFalse(run.freshness()["risk_usable"])
        self.api = Api(self.fixtures)
        self.api.markets[raw(self.pt["market"])]["timestamp"] = utc(NOW-901)
        self.assertFalse(self.capture().freshness()["risk_usable"])

    def test_stale_mark_decimals_mismatch_or_quote_identity_blocks_rescue(self):
        for mutation in ("mark", "decimals", "quote", "cache_age"):
            with self.subTest(mutation=mutation):
                self.api = Api(self.fixtures)
                if mutation == "mark":
                    for a in self.api.assets.values():
                        a["priceUpdatedAt"] = utc(NOW-121)
                elif mutation == "decimals":
                    self.api.fail = lambda method, url, params, body: Response({"result": "0x06"}) if url == RPC and body["method"] == "eth_call" else None
                elif mutation == "quote":
                    self.api.fail = lambda method, url, params, body: Response({"data": {"amountOut": "100", "amountIn": "1"}}) if url.endswith("/swap") else None
                else:
                    def cached(method, url, params, body):
                        if url.endswith("/swap"):
                            response = Response({"data": {"amountOut": "100"}})
                            response.headers["Age"] = "121"
                            return response
                    self.api.fail = cached
                run = self.capture()
                self.assertTrue(run.freshness()["risk_usable"])
                self.assertFalse(run.freshness()["execution_usable"])

    def test_elapsed_quote_and_risk_freshness_rechecked_on_every_action(self):
        run = self.capture()
        self.now += 121
        self.assertTrue(run.freshness()["risk_usable"])
        with self.assertRaises(LiveInputError):
            analyze_live(run, WSTETH, 1, rescue=True)
        self.now += 900
        with self.assertRaises(LiveInputError):
            analyze_live(run, WSTETH, 1)

    def test_incomplete_inconsistent_and_duplicate_allocations_rejected(self):
        for mutation in ("missing", "liquidity", "funded", "duplicate", "truncated"):
            with self.subTest(mutation=mutation):
                self.api = Api(self.fixtures)
                v = next(iter(self.api.vaults.values()))
                a = next(a for a in v["state"]["allocation"] if a["supplyAssetsUsd"] > 0)
                if mutation == "missing":
                    a["market"]["state"]["collateralAssetsUsd"] = None
                elif mutation == "liquidity":
                    a["market"]["state"]["liquidityAssetsUsd"] += 1_000_000
                elif mutation == "funded":
                    a["supplyAssetsUsd"] = 1e20
                elif mutation == "duplicate":
                    v["state"]["allocation"].append(copy.deepcopy(a))
                else:
                    v["state"]["allocation"].remove(a)
                self.assertFalse(self.capture().freshness()["risk_usable"])

    def test_capture_deadline_and_observation_skew_fail_closed(self):
        def advance(*args):
            self.now += 2
        self.api.fail = advance
        run = self.capture(policy=FreshnessPolicy(capture_budget_seconds=1))
        self.assertFalse(run.freshness()["risk_usable"])
        self.assertEqual(len(self.api.calls), 1)
        self.api = Api(self.fixtures)
        self.now = NOW
        for v in self.api.vaults.values():
            v["state"]["timestamp"] = NOW-200
        run = self.capture(policy=FreshnessPolicy(max_skew_seconds=100))
        self.assertFalse(run.freshness()["risk_usable"])
        self.assertTrue(any("skew" in r["reason"] for r in run.freshness()["rejections"]))

    def test_shared_markets_use_one_fresh_canonical_balance_sheet(self):
        # Nested states disagree; the dedicated market query is authoritative.
        mid, reference = None, None
        for v in self.api.vaults.values():
            for a in v["state"]["allocation"]:
                if not a["supplyAssetsUsd"]:
                    continue
                if mid is None:
                    mid, reference = a["market"]["marketId"], copy.deepcopy(a["market"])
                elif a["market"]["marketId"] == mid:
                    a["market"]["state"]["borrowAssetsUsd"] *= .9
        run = self.capture()
        self.assertIsNone(run.risk_error)
        for v in run.vault_records.values():
            for a in v["state"]["allocation"]:
                if a["market"]["marketId"] == mid:
                    self.assertEqual(a["market"]["state"], reference["state"])

    def test_solver_cannot_return_a_plan_after_execution_expiry(self):
        run = self.capture()
        def solve(*args, **kwargs):
            result = plan_rescue(*args, **kwargs)
            self.now += 121
            return result
        with patch("blast_radius.fire_drill.live.plan_rescue", side_effect=solve):
            with self.assertRaisesRegex(LiveInputError, "expired while solving"):
                analyze_live(run, WSTETH, 1, loss_limit=300_000, rescue=True)

    def test_replay_preserves_individual_retrieval_times_and_failed_runs(self):
        def advance(*args):
            self.now += 1
        self.api.fail = advance
        run = self.capture()
        rec = live_receipt(run, analyze_live(run, WSTETH, 1))
        verify_live_receipt(rec)
        self.api = Api(self.fixtures)
        self.api.fail = lambda *args: Response({}, 503)
        failed = self.capture()
        verify_live_receipt(live_receipt(failed))
        self.assertFalse(failed.freshness()["risk_usable"])

    def test_no_material_default_values_for_marks_or_market_apy(self):
        self.api.markets[raw(self.pt["market"])].pop("impliedApy")
        self.assertFalse(self.capture().freshness()["risk_usable"])
        self.api = Api(self.fixtures)
        for a in self.api.assets.values():
            a["price"]["usd"] = 0
        run = self.capture()
        self.assertTrue(run.freshness()["risk_usable"])
        self.assertFalse(run.freshness()["execution_usable"])

    def test_quote_request_slower_than_quote_ttl_is_unavailable(self):
        def slow(method, url, params, body):
            if url.endswith("/swap"):
                self.now += 121
        self.api.fail = slow
        run = self.capture(steps=(20,))
        self.assertTrue(run.freshness()["risk_usable"])
        self.assertFalse(run.freshness()["execution_usable"])
        self.assertFalse(run.bundle["positions"][self.pt["id"]]["options"][0]["available"])

    def test_unmapped_dependencies_are_disclosed_and_block_model_rescue(self):
        run = self.capture(mappings={"tokens": {}})
        self.assertTrue(run.freshness()["risk_usable"])
        self.assertFalse(run.freshness()["execution_usable"])
        self.assertTrue(any("dependency coverage" in s for s in run.execution_errors))

    def test_inactive_market_and_unadmitted_identity_rejected(self):
        self.api.active["markets"] = [m for m in self.api.active["markets"] if raw(m["address"]) != raw(self.pt["market"])]
        self.assertFalse(self.capture().freshness()["risk_usable"])
        with self.assertRaises(LiveInputError):
            self.capture([{**self.pt, "market": "0x" + "1"*40}])
        self.api = Api(self.fixtures)
        self.api.active["resumeToken"] = "another-page"
        self.assertFalse(self.capture().freshness()["risk_usable"])

    def test_explicit_risk_only_does_not_request_rpc_or_swaps(self):
        run = self.capture(steps=())
        self.assertTrue(run.freshness()["risk_usable"])
        self.assertFalse(run.freshness()["execution_usable"])
        self.assertFalse(any(c[1] == RPC or c[1].endswith("/swap") for c in self.api.calls))

    def test_morpho_only_run_does_not_depend_on_unselected_vaults(self):
        position = next(p for p in self.catalog if p["id"] == "hakutora-usdc")
        # Unselected stale data must not be fetched or used by this graph.
        next(iter(self.api.vaults.values()))["state"]["timestamp"] = NOW-3600
        run = self.capture([position])
        self.assertTrue(run.freshness()["execution_usable"], run.freshness())
        self.assertEqual(set(run.vault_records), {raw(position["vault"])})
        self.assertEqual(sum(c[1] == morpho.URL and "address" in c[3]["variables"] for c in self.api.calls), 1)
        target = next(n.id for n in run.book.graphs[position["id"]].nodes()
                      if n.kind == "token" and n.label == "cbBTC")
        analysis = analyze_live(run, target, 1, rescue=True)
        verify_live_receipt(live_receipt(run, analysis))

    def test_receipt_embeds_exact_observations_and_detects_tampering(self):
        run = self.capture()
        analysis = analyze_live(run, WSTETH, 1, loss_limit=300_000, rescue=True)
        rec = live_receipt(run, analysis)
        with tempfile.TemporaryDirectory() as directory:
            path = save_live_receipt(rec, directory)
            self.assertEqual(json.loads(path.read_text()), rec)
        rec["analysis"]["scenario"]["loss_usd"] = 1
        with self.assertRaises(LiveInputError):
            verify_live_receipt(rec)
        # Even after recalculating the integrity hash, financial reconstruction fails.
        rec.pop("receipt_sha256")
        rec["receipt_sha256"] = digest(rec)
        with self.assertRaises(LiveInputError):
            verify_live_receipt(rec)

    def test_failed_refresh_does_not_change_snapshot_files_or_baseline(self):
        paths = list((ROOT / "data/raw").glob("*.json")) + list((ROOT / "data/fire_drill").glob("*.json"))
        before = {str(p): p.read_bytes() for p in paths}
        self.capture()
        self.api.fail = lambda *args: Response({}, 503)
        self.capture()
        self.assertEqual(before, {str(p): p.read_bytes() for p in paths})
        book = prepare(load_book()["positions"])
        stress = stress_book(book, WSTETH)
        plan = plan_rescue(stress, exit_options(book), 500_000)
        self.assertAlmostEqual(stress["loss_usd"], 2_361_622.14, delta=.01)
        for field, value in (("accounted_loss_usd", 498_999.85), ("protection_cost_usd", 22_370.05),
                             ("capital_released_usd", 2_682_047.49)):
            self.assertAlmostEqual(plan["audit"][field], value, delta=.01)
        self.assertEqual({a["id"]: a["fraction"] for a in plan["actions"] if a["fraction"]},
                         {"pt-wsteth": .7, "steakhouse-eth": 1, "steakhouse-usdt": 1})


class LiveUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        LiveTests.setUpClass()

    def app(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file(str(ROOT / "app/Home.py"), default_timeout=30)
        app.query_params["fallback"] = "1"
        app.run()
        self.assertFalse(app.exception)
        return app

    def test_snapshot_default_and_one_click_fallback_need_no_network(self):
        with patch("requests.Session.request", side_effect=AssertionError("offline request")):
            app = self.app()
            self.assertEqual(app.radio(key="data_mode").value, "Snapshot Mode")
            app.radio(key="data_mode").set_value("Live Mode").run()
            self.assertFalse(app.exception)
            self.assertNotIn("live_run", app.session_state)
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.radio(key="data_mode").value, "Snapshot Mode")
            next(b for b in app.button if b.label == "Find My Weakest Point").click().run()
            self.assertAlmostEqual(app.session_state["severity"], 1)

    def test_live_ui_rejects_failed_refresh_without_displaying_previous_plan(self):
        api = Api(LiveTests.fixtures)
        client = ObservationClient(session=api, clock=lambda: NOW)
        run = capture_live([LiveTests.pt], client=client)
        with tempfile.TemporaryDirectory() as directory:
            def save(rec):
                return save_live_receipt(rec, Path(directory)/"artifacts/live")
            with patch("app.components.live.save_live_receipt", side_effect=save), patch("requests.Session.request", side_effect=AssertionError("unexpected request")):
                app = self.app()
                app.radio(key="data_mode").set_value("Live Mode").run()
                app.multiselect(key="live_selected").set_value([LiveTests.pt["id"]]).run()
                with patch("app.components.live.capture_live", return_value=run):
                    app.button(key="live_refresh").click().run()
                self.assertFalse(app.exception)
                app.button(key="live_rescue").click().run()
                self.assertFalse(app.exception)
                self.assertIsNotNone(app.session_state["live_analysis"])
                client.clock = lambda: NOW+121
                app.run()
                self.assertNotIn("live_analysis", app.session_state)
                self.assertTrue(app.button(key="live_rescue").disabled)
                client.clock = lambda: NOW
                app.run()
                app.button(key="live_rescue").click().run()
                api.fail = lambda *args: Response({}, 503)
                failed = capture_live([LiveTests.pt], client=ObservationClient(session=api, clock=lambda: NOW))
                with patch("app.components.live.capture_live", return_value=failed):
                    app.button(key="live_refresh").click().run()
                self.assertFalse(app.exception)
                self.assertNotIn("live_analysis", app.session_state)
                self.assertTrue(any("rejected" in e.value.lower() for e in app.error))

    def test_expiry_during_discovery_is_a_rejection_not_an_app_exception(self):
        run = capture_live([LiveTests.pt], client=ObservationClient(session=Api(LiveTests.fixtures), clock=lambda: NOW))
        with tempfile.TemporaryDirectory() as directory:
            with patch("app.components.live.save_live_receipt", side_effect=lambda rec: save_live_receipt(rec, Path(directory)/"artifacts/live")):
                app = self.app()
                app.radio(key="data_mode").set_value("Live Mode").run()
                app.multiselect(key="live_selected").set_value([LiveTests.pt["id"]]).run()
                with patch("app.components.live.capture_live", return_value=run):
                    app.button(key="live_refresh").click().run()
                app.button(key="live_rescue").click().run()
                self.assertIn("live_analysis", app.session_state)
                with patch("app.components.live.analyze_live", side_effect=LiveInputError("Live risk inputs expired; refresh")):
                    app.run()
                self.assertFalse(app.exception)
                self.assertNotIn("live_analysis", app.session_state)
                self.assertTrue(any("expired" in e.value for e in app.error))

    def test_refresh_to_another_instrument_removes_obsolete_locks(self):
        api = Api(LiveTests.fixtures)
        run = capture_live([LiveTests.pt], client=ObservationClient(session=api, clock=lambda: NOW))
        vault = next(p for p in load_catalog() if p["id"] == "hakutora-usdc")
        refreshed = capture_live([vault], client=ObservationClient(session=api, clock=lambda: NOW))
        with tempfile.TemporaryDirectory() as directory:
            with patch("app.components.live.save_live_receipt", side_effect=lambda rec: save_live_receipt(rec, Path(directory)/"artifacts/live")):
                app = self.app()
                app.radio(key="data_mode").set_value("Live Mode").run()
                app.multiselect(key="live_selected").set_value([LiveTests.pt["id"]]).run()
                with patch("app.components.live.capture_live", return_value=run):
                    app.button(key="live_refresh").click().run()
                app.multiselect(key="live_locks").set_value([LiveTests.pt["id"]]).run()
                app.multiselect(key="live_selected").set_value([vault["id"]]).run()
                with patch("app.components.live.capture_live", return_value=refreshed):
                    app.button(key="live_refresh").click().run()
                self.assertFalse(app.exception)
                self.assertEqual(app.multiselect(key="live_locks").value, [])
                app.button(key="live_rescue").click().run()
                self.assertFalse(app.exception)
                self.assertTrue(app.session_state["live_analysis"]["plan"]["audit"]["verified"])


if __name__ == "__main__":
    unittest.main()
