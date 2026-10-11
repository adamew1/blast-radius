"""Fail-closed live acquisition, unchanged financial rules, portable replay."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from decimal import Decimal
import json
from pathlib import Path

from ..config import ROOT, manual_map
from ..models.passthrough import PASS_THROUGH
from ..sources import morpho, pendle
from ..sources.live import (FreshnessPolicy, LiveInputError, ObservationClient,
                            check_time, digest, number, timestamp, utc)
from . import MODEL_VERSION
from .catalog import load_catalog
from .challenge import resize_positions
from .evidence import ASSUMPTIONS
from .execution import exit_options
from .model import discover, prepare, stress_book
from .optimize import plan_rescue, verify_plan

RPC = "https://ethereum-rpc.publicnode.com"
SCHEMA = "blast-radius-live-v1"
MARKET_FIELDS = """
marketId lltv
loanAsset { symbol address }
collateralAsset { symbol address }
oracle { address }
state { timestamp blockNumber supplyApy borrowApy utilization
        supplyAssetsUsd borrowAssetsUsd liquidityAssetsUsd collateralAssetsUsd }
"""
LIVE_ASSUMPTIONS = [s.replace("snapshot", "observed").replace("frozen indicative", "indicative")
                    for s in ASSUMPTIONS if "none are labelled live" not in s]
LIVE_ASSUMPTIONS += [
    "Live Mode refreshes protocol observations only; manual mappings and financial assumptions are not live.",
    "Direct PT lending-contagion discovery scans the eight admitted Morpho vaults; Morpho-only books use selected vaults. Neither covers all Morpho markets.",
    "No cash-conversion quote or certified Morpho withdrawal transaction: any model rescue is indicative, never executable.",
    "Risk and quote observations are asynchronous. No atomicity, wallet coverage or guaranteed execution is claimed.",
    "Freshness limits are application policy, not provider guarantees. Missing provider times cannot use retrieval times.",
]


def raw(address):
    value = pendle._raw(address).lower()
    if len(value) != 42 or not value.startswith("0x"):
        raise LiveInputError("Invalid token/contract identity")
    try:
        int(value[2:], 16)
    except ValueError as exc:
        raise LiveInputError("Invalid contract address") from exc
    return value


@dataclass
class LiveRun:
    positions: list
    catalog: list
    mappings: dict
    client: ObservationClient
    quote_steps: list
    market_list: dict = field(default_factory=lambda: {"markets": []})
    market_states: dict = field(default_factory=dict)
    vault_records: dict = field(default_factory=dict)
    bundle: dict = field(default_factory=lambda: {"positions": {}})
    checks: list = field(default_factory=list)
    execution_errors: list = field(default_factory=list)
    risk_error: str | None = None
    book: object = None
    completed_at: float = 0

    def markets_active(self, chain_id=1):
        return self.market_list

    def market_data(self, address, chain_id=1):
        return self.market_states[raw(address)]

    def vault_by_address(self, address, chain_id=1):
        return self.vault_records[raw(address)]

    def vaults(self, chain_ids=(1,), first=50):
        return list(self.vault_records.values())

    def record_time(self, value, kind, label):
        policy = self.client.policy
        limit = {"risk": policy.risk_seconds, "mark": policy.mark_seconds,
                 "quote": policy.quote_seconds, "rpc": policy.rpc_seconds}[kind]
        observed = check_time(value, self.client.clock(), limit, policy, label)
        self.checks.append({"kind": kind, "label": label, "observed_at": observed, "max_age_seconds": limit})

    def freshness(self, now=None):
        now = self.client.clock() if now is None else now
        rejected, rows = [], []
        for c in self.checks:
            try:
                check_time(c["observed_at"], now, c["max_age_seconds"], self.client.policy, c["label"])
                status = "fresh"
            except LiveInputError as exc:
                status = "stale"
                rejected.append({"kind": c["kind"], "reason": str(exc)})
            rows.append({**c, "age_seconds": now - c["observed_at"], "status": status})
        risk_times = [c["observed_at"] for c in self.checks if c["kind"] == "risk"]
        if risk_times and max(risk_times) - min(risk_times) > self.client.policy.max_skew_seconds:
            rejected.append({"kind": "risk", "reason": "Risk observation skew exceeds policy"})
        risk_ok = bool(risk_times) and not self.risk_error and not any(r["kind"] == "risk" for r in rejected)
        execution_ok = risk_ok and not self.execution_errors and not rejected
        return {"checked_at": utc(now), "risk_usable": risk_ok, "execution_usable": execution_ok,
                "status": "fresh observations; manual assumptions remain" if execution_ok else
                          "risk-only" if risk_ok else "rejected",
                "fully_live": False, "executable": False, "checks": rows, "rejections": rejected,
                "risk_error": self.risk_error, "execution_errors": self.execution_errors,
                "as_of_window_utc": [utc(min(risk_times)), utc(max(risk_times))] if risk_times else [],
                "policy": self.client.policy.to_dict()}


def validate_positions(positions, catalog):
    sizes = {p["id"]: 0 for p in catalog}
    sizes.update({p["id"]: p["size_usd"] for p in positions})
    if resize_positions(catalog, sizes) != positions:
        raise LiveInputError("Unsupported instrument, duplicate, or changed catalog identity")


def validate_vault(run, vault, expected, shared):
    if not vault or raw(vault["address"]) != raw(expected["vault"]) or vault["chain"]["id"] != 1:
        raise LiveInputError("Morpho vault identity/chain mismatch")
    state = vault["state"]
    total = number(state["totalAssetsUsd"], "vault total assets", positive=True)
    number(state["netApy"], "vault net APY", signed=True)
    run.record_time(state.get("timestamp"), "risk", expected["id"])
    if not isinstance(state.get("allocation"), list) or not state["allocation"]:
        raise LiveInputError("Missing vault allocations")
    seen, funded = set(), 0.0
    for a in state["allocation"]:
        supply = number(a["supplyAssetsUsd"], "funded allocation")
        funded += supply
        m = a["market"]
        mid = m["marketId"]
        if mid in seen:
            raise LiveInputError("Duplicate vault market allocation")
        seen.add(mid)
        if not supply:
            continue
        raw(m["loanAsset"]["address"])
        if raw(m["loanAsset"]["address"]) != raw(vault["asset"]["address"]):
            raise LiveInputError("Allocation loan asset differs from vault asset")
        s = m["state"]
        run.record_time(s.get("timestamp"), "risk", mid)
        values = {k: number(s[k], k) for k in ("supplyAssetsUsd", "borrowAssetsUsd", "liquidityAssetsUsd")}
        market_supply, debt, liquidity = (values[k] for k in ("supplyAssetsUsd", "borrowAssetsUsd", "liquidityAssetsUsd"))
        tolerance = max(.02, market_supply * 1e-6)
        if (supply > market_supply + tolerance or debt > market_supply + tolerance
                or abs(liquidity - (market_supply - debt)) > tolerance):
            raise LiveInputError("Inconsistent lending-market supply/debt/liquidity or funded claim")
        for k in ("supplyApy", "borrowApy"):
            number(s[k], k, signed=True)
        if debt and not m.get("collateralAsset"):
            raise LiveInputError("Funded debt has no collateral identity")
        if m.get("collateralAsset"):
            number(s["collateralAssetsUsd"], "collateralAssetsUsd")
            raw(m["collateralAsset"]["address"])
            raw(m["oracle"]["address"])
            lltv = number(m["lltv"], "LLTV") / 1e18
            if lltv > 1:
                raise LiveInputError("Invalid LLTV")
        signature = {k: m[k] for k in ("loanAsset", "collateralAsset", "oracle", "lltv", "state")}
        if mid in shared and shared[mid] != signature:
            raise LiveInputError("Shared market observations disagree across vaults; refresh the run")
        shared[mid] = signature
    if abs(funded - total) > max(.02, total * 1e-6):
        raise LiveInputError("Allocations do not reconcile to vault assets; idle/unreported assets require separate evidence")


def acquire_risk(run):
    # Direct PT positions scan every admitted vault for lending contagion. Vault
    # positions only depend on their own funded allocations; unrelated vaults must
    # not become implicit material inputs to a Morpho-only analysis.
    has_direct_pt = any(p["kind"] == "pendle_pt" for p in run.positions)
    vault_scope = run.catalog if has_direct_pt else run.positions
    fields = morpho._VAULT_FIELDS.replace("totalAssetsUsd apy", "timestamp blockNumber totalAssets totalAssetsUsd apy")
    fields = fields.replace("supplyAssetsUsd supplyCapUsd", "supplyAssets supplyAssetsUsd supplyCapUsd")
    fields = fields.replace("state { utilization", "state { timestamp blockNumber supplyApy borrowApy utilization")
    query = "query($address:String!, $chainId:Int!){vaultByAddress(address:$address,chainId:$chainId){" + fields + "}}"
    for p in vault_scope:
        if p["kind"] != "morpho_vault":
            continue
        data, _ = run.client.post(morpho.URL, {"query": query, "variables": {"address": p["vault"], "chainId": 1}})
        vault = data["data"]["vaultByAddress"]
        if not vault or raw(vault["address"]) != raw(p["vault"]):
            raise LiveInputError("Morpho vault identity mismatch")
        run.vault_records[raw(p["vault"])] = vault
    # Nested vault market states may be indexed at different times. Obtain one
    # fresh, canonical state for each funded market, preserving all raw responses.
    mids = sorted({a["market"]["marketId"] for v in run.vault_records.values()
                   for a in v["state"]["allocation"] if a["supplyAssetsUsd"] > 0})
    canonical = {}
    for start in range(0, len(mids), 20):
        batch = mids[start:start+20]
        variables = {f"m{i}": mid for i, mid in enumerate(batch)}
        declarations = ",".join(f"${k}:String!" for k in variables)
        selections = " ".join(f"{k}:marketById(marketId:${k},chainId:1){{{MARKET_FIELDS}}}" for k in variables)
        data, _ = run.client.post(morpho.URL, {"query": f"query({declarations}){{{selections}}}", "variables": variables})
        for key, mid in variables.items():
            market = data["data"][key]
            if not market or market["marketId"] != mid:
                raise LiveInputError("Canonical market identity mismatch or missing state")
            canonical[mid] = market
    for vault in run.vault_records.values():
        for a in vault["state"]["allocation"]:
            if not a["supplyAssetsUsd"]:
                continue
            embedded = a["market"]
            market = canonical[embedded["marketId"]]
            for key in ("loanAsset", "collateralAsset", "oracle"):
                old, new = embedded.get(key), market.get(key)
                if bool(old) != bool(new) or (old and raw(old["address"]) != raw(new["address"])):
                    raise LiveInputError("Market identity disagrees between vault and canonical observations")
            if embedded["lltv"] != market["lltv"]:
                raise LiveInputError("Market LLTV disagrees across observations")
            a["market"] = copy.deepcopy(market)
    shared = {}
    for p in vault_scope:
        if p["kind"] == "morpho_vault":
            validate_vault(run, run.vault_records[raw(p["vault"])], p, shared)
    active, _ = run.client.get(f"{pendle.BASE}/v1/1/markets/active")
    if not isinstance(active.get("markets"), list) or not active["markets"]:
        raise LiveInputError("Pendle active market list unavailable")
    if active.get("resumeToken") or active.get("hasNextPage"):
        raise LiveInputError("Incomplete Pendle universe: pagination is not supported by this adapter")
    index, pt_ids = {}, set()
    for m in active["markets"]:
        address, pt = raw(m["address"]), raw(m["pt"])
        raw(m["underlyingAsset"])
        if address in index or pt in pt_ids:
            raise LiveInputError("Duplicate Pendle identity")
        index[address] = m
        pt_ids.add(pt)
    required = {raw(p["market"]) for p in run.positions if p["kind"] == "pendle_pt"}
    if required - index.keys():
        raise LiveInputError("Selected Pendle market no longer active/supported")
    collateral = {raw(a["market"]["collateralAsset"]["address"])
                  for v in run.vault_records.values() for a in v["state"]["allocation"]
                  if a["supplyAssetsUsd"] > 0 and a["market"].get("collateralAsset")}
    required |= {addr for addr, m in index.items() if raw(m["pt"]) in collateral}
    for addr in sorted(required):
        m = index[addr]
        if timestamp(m["expiry"]) <= run.client.clock():
            raise LiveInputError("Expired Pendle market")
        md, _ = run.client.get(f"{pendle.BASE}/v2/1/markets/{m['address']}/data")
        run.record_time(md.get("timestamp"), "risk", "Pendle market " + addr)
        number(md["impliedApy"], "Pendle implied APY", signed=True)
        number(md["liquidity"]["usd"], "Pendle liquidity")
        # All financial details used by discovery come from timestamp-checked /data.
        m["details"] = {"impliedApy": md["impliedApy"], "liquidity": md["liquidity"]["usd"]}
        run.market_states[addr] = md
        run.market_list["markets"].append(m)
    run.book = prepare(run.positions, provider=run, mappings=run.mappings)
    for p in run.positions:
        g = run.book.graphs[p["id"]]
        if len(g.nodes()) <= 1:
            raise LiveInputError("Discovery produced an unresolved position")
        if any(n.meta.get("unmapped") for n in g.nodes()):
            run.execution_errors.append(p["id"] + ": incomplete manually mapped dependency coverage")


def rpc_call(run, method, params):
    result, key = run.client.post(RPC, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if result.get("error") or result.get("result") is None:
        raise LiveInputError("RPC returned no result")
    return result["result"], key


def capture_quotes(run):
    pts = [p for p in run.positions if p["kind"] == "pendle_pt"]
    if not run.quote_steps:
        run.execution_errors.append("Risk-only capture requested; no execution optimization")
        return
    if not pts:
        return
    block, _ = rpc_call(run, "eth_getBlockByNumber", ["latest", False])
    run.record_time(int(block["timestamp"], 16), "rpc", "Ethereum decimals block")
    run.bundle.update({"rpc": RPC, "rpc_block": block["number"], "rpc_block_timestamp": int(block["timestamp"], 16)})
    assets = {}

    def asset(address):
        addr = raw(address)
        if addr in assets:
            return assets[addr]
        data, key = run.client.get(f"{pendle.BASE}/v1/1/assets/{addr}")
        if raw(data["address"]) != addr or data["chainId"] != 1:
            raise LiveInputError("Pendle asset identity mismatch")
        run.record_time(data.get("priceUpdatedAt"), "mark", "USD mark " + addr)
        price = number(data["price"]["usd"], "asset USD mark", positive=True)
        decimals, rpc_key = rpc_call(run, "eth_call", [{"to": addr, "data": "0x313ce567"}, block["number"]])
        decimals = int(decimals, 16)
        if decimals != data["decimals"] or not 0 <= decimals <= 36:
            raise LiveInputError("RPC/API token decimals disagree or unsupported")
        assets[addr] = {"address": addr, "decimals": decimals, "price_usd": price,
                        "price_updated_at": data["priceUpdatedAt"], "symbol": data["symbol"],
                        "observation_key": key, "rpc_observation_key": rpc_key}
        return assets[addr]

    for p in pts:
        try:
            m = next(m for m in run.market_list["markets"] if raw(m["address"]) == raw(p["market"]))
            inp, output = asset(m["pt"]), asset(m["underlyingAsset"])
            record = {"position": p, "input_asset": inp, "output_asset": output, "options": []}
            run.bundle["positions"][p["id"]] = record
            for step in run.quote_steps:
                # Integer input rounding must be reflected in sold notional. Never
                # scale output to a target USD allocation or to another trade size.
                target = Decimal(p["size_usd"]) * Decimal(step) / 20
                amount = int(target / Decimal(str(inp["price_usd"])) * 10 ** inp["decimals"])
                notional = float(Decimal(amount) / 10 ** inp["decimals"] * Decimal(str(inp["price_usd"])))
                if amount <= 0 or notional > p["size_usd"]:
                    raise LiveInputError("Unsupported rounded token input")
                q = {"notional_usd": notional, "fraction": notional / p["size_usd"],
                     "grid_step": step, "amount_in": str(amount), "available": False}
                record["options"].append(q)
                try:
                    params = {"receiver": pendle.DEFAULT_RECEIVER, "slippage": .01,
                              "tokenIn": inp["address"], "tokenOut": output["address"], "amountIn": str(amount)}
                    url = f"{pendle.BASE}/v2/sdk/1/markets/{p['market']}/swap"
                    data, key = run.client.get(url, params)
                    quote = data["data"]
                    amount_out = str(quote["amountOut"])
                    if not amount_out.isdecimal() or int(amount_out) <= 0:
                        raise LiveInputError("Invalid quote amountOut")
                    # A response may echo identity; reject any disagreement.
                    for field, expected in (("amountIn", str(amount)), ("tokenIn", inp["address"]), ("tokenOut", output["address"])):
                        if field in quote and str(quote[field]).lower() != expected.lower():
                            raise LiveInputError("Quote input/output identity mismatch")
                    observation = run.client._memo[key]
                    # SDK quotes lack a state timestamp. Their freshness is only
                    # the request interval, explicitly not chain-state atomicity.
                    headers = {k.lower(): v for k, v in observation.get("headers", {}).items()}
                    cached_age = number(headers.get("age", 0), "quote HTTP cache age")
                    run.record_time(observation["requested_at"] - cached_age, "quote", "Quote " + key)
                    value = float(Decimal(amount_out) / 10 ** output["decimals"] * Decimal(str(output["price_usd"])))
                    number(value, "quoted output value", positive=True)
                    q.update({"available": True, "amount_out": amount_out, "output_value_usd": value,
                              "mark_shortfall_usd": max(0, notional - value), "raw_cache_key": key,
                              "params": params, "captured_at": utc(observation["received_at"]),
                              "timestamp_semantics": "request time only; SDK state time unavailable"})
                except (LiveInputError, KeyError, TypeError, ValueError, OverflowError) as exc:
                    q["error"] = str(exc)
            if not any(q["available"] for q in record["options"]):
                run.execution_errors.append(p["id"] + ": no valid exact-size quotes")
        except (LiveInputError, KeyError, TypeError, ValueError, OverflowError) as exc:
            run.execution_errors.append(p["id"] + ": " + str(exc))


def capture_live(positions, *, client=None, quote_steps=(5, 10, 15, 20), catalog=None, mappings=None):
    catalog = copy.deepcopy(load_catalog() if catalog is None else catalog)
    validate_positions(positions, catalog)
    if (len(set(quote_steps)) != len(quote_steps)
            or any(type(s) is not int or not 1 <= s <= 20 for s in quote_steps)):
        raise LiveInputError("Quote steps must be distinct integers on the existing 5% grid")
    run = LiveRun(copy.deepcopy(positions), catalog, copy.deepcopy(manual_map() if mappings is None else mappings),
                  client or ObservationClient(), sorted(quote_steps))
    try:
        acquire_risk(run)
    except (LiveInputError, KeyError, TypeError, ValueError, OverflowError, StopIteration) as exc:
        run.risk_error = f"Risk inputs rejected: {exc}"
        run.book = None
    if run.book:
        try:
            capture_quotes(run)
        except (LiveInputError, KeyError, TypeError, ValueError, OverflowError) as exc:
            run.execution_errors.append("Execution inputs rejected: " + str(exc))
    run.completed_at = run.client.clock()
    run.bundle["captured_at"] = utc(run.completed_at)
    return run


def live_candidates(run, now=None):
    status = run.freshness(now)
    if not status["execution_usable"]:
        raise LiveInputError("Risk-only: complete fresh execution evidence required")
    result = exit_options(run.book, run.bundle)
    # The financial arithmetic above is unchanged; replace snapshot-only prose.
    for options in result["options"].values():
        for option in options:
            if option["source"] == "cached Morpho funded allocations and market liquidity":
                option["source"] = "fresh Morpho funded claims and shared liquidity; withdrawal not certified"
    for row in result["unavailable"]:
        row["reason"] = row["reason"].replace("snapshot", "observed")
    return result


def analyze_live(run, dependency, severity, *, loss_limit=500_000, locks=(), rescue=False, now=None):
    locks = sorted(set(locks))
    check_after_solve = now is None
    now = run.client.clock() if now is None else now
    status = run.freshness(now)
    if not status["risk_usable"] or run.book is None:
        raise LiveInputError("Live risk inputs rejected or expired; refresh or select Snapshot Mode")
    stress = stress_book(run.book, dependency, severity)
    candidates, plan = None, None
    if status["execution_usable"]:
        candidates = live_candidates(run, now)
        if rescue:
            plan = plan_rescue(stress, candidates, loss_limit, list(locks))
            plan["classification"] = "indicative model rescue; not executable"
            plan["executable"] = False
            if check_after_solve:
                now = run.client.clock()
                status = run.freshness(now)
                if not status["execution_usable"]:
                    raise LiveInputError("Execution evidence expired while solving; refresh the run")
    elif rescue:
        raise LiveInputError("Risk-only analysis: execution evidence missing, incomplete or stale")
    return {"analyzed_at": now, "freshness": status, "scenario": stress,
            "exit_candidates": candidates, "plan": plan, "loss_limit": loss_limit, "locks": list(locks)}


def live_receipt(run, analysis=None):
    payload = {"receipt_schema": SCHEMA, "model_version": MODEL_VERSION,
               "classification": "fresh protocol observations with manual mappings and financial assumptions",
               "executable": False, "portfolio": run.positions, "catalog": run.catalog,
               "manual_mappings": run.mappings, "policy": run.client.policy.to_dict(),
               "capture_started_at": run.client.started_at, "capture_completed_at": run.completed_at,
               "morpho_discovery_scope": {
                   "vaults": sorted(run.vault_records),
                   "rule": "all admitted vaults for direct PT contagion; selected vaults for Morpho-only books"},
               "quote_steps": run.quote_steps, "observations": run.client.observations,
               "freshness_at_capture": run.freshness(run.completed_at), "analysis": analysis,
               "assumptions": LIVE_ASSUMPTIONS,
               "coefficients": {**PASS_THROUGH, "pt_underlying_claim_override": 1.0},
               "timestamp_semantics": "Provider state/mark times are separate from retrieval and quote request times. No atomicity.",
               "code_hashes": {str(p.relative_to(ROOT)).replace("\\", "/"): digest(p.read_text(encoding="utf-8"))
                               for p in sorted((ROOT / "blast_radius").rglob("*.py"))}}
    payload["receipt_sha256"] = digest(payload)
    return copy.deepcopy(payload)


def save_live_receipt(rec, directory=None):
    directory = Path(directory) if directory is not None else ROOT / "artifacts/live"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (rec["receipt_sha256"] + ".json")
    path.write_text(json.dumps(rec, indent=2, allow_nan=False), encoding="utf-8")
    return path


def verify_live_receipt(rec):
    """Reacquire from exact embedded responses, never from the network or cache."""
    payload = copy.deepcopy(rec)
    expected = payload.pop("receipt_sha256")
    if digest(payload) != expected or rec["receipt_schema"] != SCHEMA or rec["model_version"] != MODEL_VERSION:
        raise LiveInputError("Receipt hash/schema/model mismatch")
    for name, code_hash in rec["code_hashes"].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or digest(path.read_text(encoding="utf-8")) != code_hash:
            raise LiveInputError("Receipt model source differs: " + name)
    # Validate against the admitted universe as well as the embedded catalog.
    if rec["catalog"] != load_catalog():
        raise LiveInputError("Receipt changes the admitted catalog")
    client = ObservationClient(clock=lambda: rec["capture_started_at"],
                               policy=FreshnessPolicy(**rec["policy"]), replay=rec["observations"])
    client.started_at = rec["capture_started_at"]
    run = capture_live(rec["portfolio"], client=client, quote_steps=rec["quote_steps"],
                       catalog=rec["catalog"], mappings=rec["manual_mappings"])
    run.completed_at = rec["capture_completed_at"]
    run.bundle["captured_at"] = utc(run.completed_at)
    if sorted(run.vault_records) != rec["morpho_discovery_scope"]["vaults"]:
        raise LiveInputError("Morpho discovery scope does not reproduce")
    if run.freshness(run.completed_at) != rec["freshness_at_capture"]:
        raise LiveInputError("Capture freshness does not reproduce")
    analysis = rec["analysis"]
    if analysis:
        rebuilt = analyze_live(run, analysis["scenario"]["dependency_id"], analysis["scenario"]["severity"],
                               loss_limit=analysis["loss_limit"], locks=analysis["locks"],
                               rescue=False, now=analysis["analyzed_at"])
        if (rebuilt["scenario"] != analysis["scenario"] or rebuilt["exit_candidates"] != analysis["exit_candidates"]
                or rebuilt["freshness"] != analysis["freshness"]):
            raise LiveInputError("Live scenario/candidates do not reproduce")
        plan = analysis["plan"]
        if plan:
            if (not rebuilt["freshness"]["execution_usable"] or plan["locks"] != analysis["locks"]
                    or plan["loss_limit_usd"] != analysis["loss_limit"] or plan.get("executable") is not False):
                raise LiveInputError("Plan mandate differs or execution evidence is unavailable")
            if plan.get("optimal") and not plan.get("audit"):
                raise LiveInputError("Optimal plan has no financial audit")
        if plan and plan.get("audit"):
            audit = verify_plan(rebuilt["scenario"], rebuilt["exit_candidates"], plan["actions"], plan["withdrawals"],
                                plan["locks"], plan["loss_limit_usd"])
            if audit != plan["audit"] or plan.get("executable") is not False:
                raise LiveInputError("Live plan audit does not reproduce")
    return run
