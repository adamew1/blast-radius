"""Morpho native-unit adapter; leaves the validated financial engine unchanged.

Raw HTTP responses remain intact. Display USD fields are rebuilt from integer
token balances and one timestamped price per token, then passed to the existing
validator. Version 2 receipts replay this adapter before replaying the model.
"""
from __future__ import annotations

import copy
from decimal import Decimal

from blast_radius.config import ROOT
from blast_radius.fire_drill import live as engine
from blast_radius.fire_drill.catalog import load_catalog
from blast_radius.sources import morpho
from blast_radius.sources.live import (FreshnessPolicy, LiveInputError, ObservationClient,
                                       check_time, digest, number, utc)

SCHEMA = "blast-radius-native-live-v2"
ADAPTER = "app/live_data.py"


def integer(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, str)) or not str(value).isdecimal():
        raise LiveInputError(f"Missing or invalid integer native balance: {label}")
    return int(value)


class NativeObservationClient(ObservationClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.normalization = {"method": "integer native balances; one observed USD price per token per run",
                              "prices": {}, "vaults": {}, "markets": {}}

    def price(self, asset, key):
        address = engine.raw(asset["address"])
        decimals = asset.get("decimals")
        if type(decimals) is not int or not 0 <= decimals <= 36:
            raise LiveInputError("Missing/invalid token decimals for " + address)
        prices = self.normalization["prices"]
        if address in prices:
            if prices[address]["decimals"] != decimals:
                raise LiveInputError("Morpho token decimals disagree across observations: " + address)
            return prices[address]
        mark = asset.get("price") or {}
        value = number(mark.get("usd"), "Morpho risk-token USD price " + address, positive=True)
        observed = check_time(mark.get("timestamp"), self.clock(), self.policy.risk_seconds,
                              self.policy, "Morpho risk-token price " + address)
        prices[address] = {"address": address, "symbol": asset.get("symbol", address), "decimals": decimals,
                           "usd": value, "timestamp": observed, "observation_key": key,
                           "role": "risk valuation; not an execution quote mark"}
        return prices[address]

    @staticmethod
    def usd(amount, mark):
        return float(Decimal(amount) * Decimal(str(mark["usd"])) / Decimal(10) ** mark["decimals"])

    def market(self, market, key):
        state = market["state"]
        loan = self.price(market["loanAsset"], key)
        supply, debt, liquidity = [integer(state.get(k), market["marketId"] + " " + k)
                                   for k in ("supplyAssets", "borrowAssets", "liquidityAssets")]
        # A one-base-unit difference accommodates integer rounding, never USD
        # display drift. Debt above supply is always rejected.
        if debt > supply or abs(supply - debt - liquidity) > 1:
            raise LiveInputError("Inconsistent native supply/debt/liquidity for " + market["marketId"])
        report = {"observation_key": key, "loan_asset": loan["address"],
                  "native_supply": str(supply), "native_debt": str(debt), "native_liquidity": str(liquidity),
                  "reported_usd": {k: state.get(k) for k in
                                   ("supplyAssetsUsd", "borrowAssetsUsd", "liquidityAssetsUsd", "collateralAssetsUsd")}}
        for name, amount in (("supplyAssetsUsd", supply), ("borrowAssetsUsd", debt), ("liquidityAssetsUsd", liquidity)):
            state[name] = self.usd(amount, loan)
        collateral = market.get("collateralAsset")
        if collateral:
            mark = self.price(collateral, key)
            amount = integer(state.get("collateralAssets"), market["marketId"] + " collateralAssets")
            state["collateralAssetsUsd"] = self.usd(amount, mark)
            report.update(collateral_asset=mark["address"], native_collateral=str(amount))
        elif debt:
            raise LiveInputError("Funded native debt has no collateral identity")
        report["normalized_usd"] = {k: state.get(k) for k in report["reported_usd"]}
        self.normalization["markets"][market["marketId"]] = report

    def vault(self, vault, key):
        state = vault["state"]
        mark = self.price(vault["asset"], key)
        total = integer(state.get("totalAssets"), "vault totalAssets")
        allocations = state["allocation"]
        funded, count = 0, 0
        report = {"observation_key": key, "asset": mark["address"], "native_total": str(total),
                  "reported_total_usd": state["totalAssetsUsd"], "allocations": {}}
        for allocation in allocations:
            amount = integer(allocation.get("supplyAssets"), "vault funded allocation")
            funded += amount
            if amount:
                count += 1
                self.market(allocation["market"], key)
                if engine.raw(allocation["market"]["loanAsset"]["address"]) != mark["address"]:
                    raise LiveInputError("Native allocation loan asset differs from vault asset")
            report["allocations"][allocation["market"]["marketId"]] = {
                "native_claim": str(amount), "reported_usd": allocation["supplyAssetsUsd"]}
            allocation["supplyAssetsUsd"] = self.usd(amount, mark)
        if abs(total - funded) > max(1, count):
            raise LiveInputError("Native allocations do not reconcile to vault assets; idle/unreported assets require evidence")
        state["totalAssetsUsd"] = self.usd(total, mark)
        report.update(native_funded=str(funded), normalized_total_usd=state["totalAssetsUsd"])
        self.normalization["vaults"][engine.raw(vault["address"])] = report

    def post(self, url, body):
        if url != morpho.URL:
            return super().post(url, body)
        body = copy.deepcopy(body)
        query = body["query"]
        for name in ("loanAsset", "collateralAsset"):
            query = query.replace(name + " { symbol address }",
                                  name + " { symbol address decimals price { usd timestamp } }")
        query = query.replace("asset { symbol address decimals }", "asset { symbol address decimals price { usd timestamp } }")
        query = query.replace("state { timestamp blockNumber supplyApy",
                              "state { timestamp blockNumber supplyAssets borrowAssets liquidityAssets collateralAssets supplyApy")
        body["query"] = query
        data, key = super().post(url, body)
        # super().post already deep-copied the response: the raw observations and
        # their hashes retain the exact provider display values and native units.
        try:
            records = data["data"]
            if "vaultByAddress" in records:
                self.vault(records["vaultByAddress"], key)
            else:
                for market in records.values():
                    self.market(market, key)
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
            if isinstance(exc, LiveInputError):
                raise
            raise LiveInputError("Incomplete native Morpho response: " + str(exc)) from exc
        return data, key


def capture_live(positions, *, client=None, **kwargs):
    if not isinstance(client, NativeObservationClient):
        if client is not None and client.observations:
            raise LiveInputError("Native capture requires a new, empty observation client")
        client = NativeObservationClient(**({"session": client.session, "clock": client.clock, "policy": client.policy}
                                             if client is not None else {}))
    run = engine.capture_live(positions, client=client, **kwargs)
    try:
        for mark in client.normalization["prices"].values():
            run.record_time(mark["timestamp"], "risk", "Morpho risk-token price " + mark["address"])
    except LiveInputError as exc:
        run.risk_error = "Risk inputs rejected: " + str(exc)
        run.book = None
    run.completed_at = client.clock()
    run.bundle["captured_at"] = utc(run.completed_at)
    return run


def live_receipt(run, analysis=None):
    rec = engine.live_receipt(run, analysis)
    if not isinstance(run.client, NativeObservationClient):
        return rec  # Existing sessions and original v1 receipts remain replayable.
    rec["receipt_schema"] = SCHEMA
    rec["normalization"] = copy.deepcopy(run.client.normalization)
    rec["adapter_code_hashes"] = {ADAPTER: digest((ROOT / ADAPTER).read_text(encoding="utf-8"))}
    rec.pop("receipt_sha256")
    rec["receipt_sha256"] = digest(rec)
    return rec


def verify_live_receipt(rec):
    if rec.get("receipt_schema") != SCHEMA:
        return engine.verify_live_receipt(rec)
    payload = copy.deepcopy(rec)
    expected = payload.pop("receipt_sha256")
    if digest(payload) != expected or rec["model_version"] != engine.MODEL_VERSION:
        raise LiveInputError("Native receipt hash/schema/model mismatch")
    code = {str(p.relative_to(ROOT)).replace("\\", "/"): digest(p.read_text(encoding="utf-8"))
            for p in sorted((ROOT / "blast_radius").rglob("*.py"))}
    if rec["code_hashes"] != code or rec["adapter_code_hashes"] != {ADAPTER: digest((ROOT / ADAPTER).read_text(encoding="utf-8"))}:
        raise LiveInputError("Native receipt financial model or adapter source differs")
    if rec["catalog"] != load_catalog():
        raise LiveInputError("Native receipt changes admitted catalog")
    client = NativeObservationClient(clock=lambda: rec["capture_started_at"],
                                     policy=FreshnessPolicy(**rec["policy"]), replay=rec["observations"])
    run = capture_live(rec["portfolio"], client=client, quote_steps=rec["quote_steps"],
                       catalog=rec["catalog"], mappings=rec["manual_mappings"])
    run.completed_at = rec["capture_completed_at"]
    run.bundle["captured_at"] = utc(run.completed_at)
    if (client.observations != rec["observations"] or client.normalization != rec["normalization"]
            or run.freshness(run.completed_at) != rec["freshness_at_capture"]
            or sorted(run.vault_records) != rec["morpho_discovery_scope"]["vaults"]):
        raise LiveInputError("Native observations, normalization, scope or freshness do not reproduce")
    analysis = rec["analysis"]
    if analysis:
        rebuilt = engine.analyze_live(run, analysis["scenario"]["dependency_id"], analysis["scenario"]["severity"],
                                      loss_limit=analysis["loss_limit"], locks=analysis["locks"], now=analysis["analyzed_at"])
        for key in ("scenario", "exit_candidates", "freshness"):
            if rebuilt[key] != analysis[key]:
                raise LiveInputError("Native analysis does not reproduce: " + key)
        plan = analysis["plan"]
        if plan:
            if (not rebuilt["freshness"]["execution_usable"] or plan["locks"] != analysis["locks"]
                    or plan["loss_limit_usd"] != analysis["loss_limit"] or plan.get("executable") is not False):
                raise LiveInputError("Native plan mandate differs or execution evidence is unavailable")
            if plan.get("optimal") and not plan.get("audit"):
                raise LiveInputError("Native optimal plan has no financial audit")
            if plan.get("audit"):
                audit = engine.verify_plan(rebuilt["scenario"], rebuilt["exit_candidates"], plan["actions"],
                                           plan["withdrawals"], plan["locks"], plan["loss_limit_usd"])
                if audit != plan["audit"]:
                    raise LiveInputError("Native plan audit does not reproduce")
    return run


save_live_receipt = engine.save_live_receipt
