"""Independent audit: reads raw responses; never calls the product's financial engine.

Decimal arithmetic reconstructs the wstETH stress and all candidate economics.
Exhaustive enumeration proves the headline grid objective independently of MILP.
"""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
D = lambda x: Decimal(str(x))
ZERO = D(0)
WSTETH = "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0"
RAW = {}
USED = set()
for path in (ROOT / "data/raw").glob("*.json"):
    RAW[path.stem] = json.loads(path.read_text(encoding="utf-8"))


def key(method, url, params=None, body=None):
    payload = json.dumps({"m": method, "u": url, "p": params, "b": body}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:20]


def labelled(label):
    matches = [(k, v) for k, v in RAW.items() if v["meta"].get("label") == label]
    assert len(matches) == 1, (label, len(matches))
    k, v = matches[0]
    USED.add(k)
    return v


def close(actual, expected, reason, tolerance=D("0.02")):
    assert abs(D(actual) - D(expected)) <= tolerance, (reason, actual, expected)


def utc(value):
    return datetime.fromtimestamp(float(value), timezone.utc).isoformat()


def main():
    sample = json.loads((ROOT / "data/book/sample_book.json").read_text())
    book = sample["positions"]
    bundle = json.loads((ROOT / "data/fire_drill/execution.json").read_text())
    rec = json.loads((ROOT / "artifacts/fire_drill_receipt.json").read_text())
    active = labelled("pendle_active:1")["data"]["markets"]
    pt_index = {m["pt"].split("-", 1)[-1].lower(): m for m in active}
    markets = {m["address"].lower(): m for m in active}
    vaults, loss, apy, details, candidates = {}, {}, {}, [], {}
    resources, caps = {}, {}

    # This headline shock reaches directly observed wstETH collateral, with no
    # issuer prior, oracle hypothesis, or manually chosen portfolio membership.
    def token_shock(addr):
        addr = addr.lower()
        if addr == WSTETH:
            return D(1)
        if addr in pt_index:
            return token_shock(pt_index[addr]["underlyingAsset"].split("-", 1)[-1])
        return ZERO

    for p in book:
        pid, size = p["id"], D(p["size_usd"])
        if p["kind"] == "pendle_pt":
            m = markets[p["market"].lower()]
            loss[pid] = size * token_shock(m["underlyingAsset"].split("-", 1)[-1])
            apy[pid] = max(ZERO, D(m["details"].get("impliedApy") or 0))
        else:
            v = labelled("morpho_vault:" + p["vault"])["data"]["data"]["vaultByAddress"]
            assert v["address"].lower() == p["vault"].lower()
            vaults[pid] = v
            state = v["state"]
            total = D(state["totalAssetsUsd"])
            apy[pid] = max(ZERO, D(state["netApy"] if state["netApy"] is not None else state["apy"]))
            loss[pid], caps[pid] = ZERO, {}
            for a in state["allocation"]:
                m, supplied = a["market"], D(a["supplyAssetsUsd"] or 0)
                s = m["state"]
                mid = m["marketId"]
                liquidity = s["liquidityAssetsUsd"]
                if supplied > 0 and liquidity is not None:
                    capacity = max(ZERO, D(liquidity))
                    caps[pid][mid] = caps[pid].get(mid, ZERO) + min(supplied, capacity)
                    resources[mid] = min(resources.get(mid, capacity), capacity)
                collateral = m["collateralAsset"]
                if not collateral or supplied <= 0:
                    continue
                # Match the declared discovery coverage cutoff, independently.
                if round(float(100 * supplied / total), 2) < .1:
                    continue
                shock = token_shock(collateral["address"])
                if not shock:
                    continue
                supply, debt, backing = (D(s[k]) for k in
                    ("supplyAssetsUsd", "borrowAssetsUsd", "collateralAssetsUsd"))
                base = max(ZERO, debt - backing)
                shortfall = max(ZERO, debt - backing * (1 - shock)) - base
                market_loss = min(D(1), max(ZERO, shortfall / supply))
                dollars = size * supplied / total * market_loss
                loss[pid] += dollars
                details.append({"position": pid, "market": mid, "collateral": collateral["address"],
                    "allocation_usd": float(supplied), "vault_assets_usd": float(total),
                    "market_supply_usd": float(supply), "market_debt_usd": float(debt),
                    "market_collateral_usd": float(backing), "collateral_shock": float(shock),
                    "position_loss_usd": float(dollars)})
        close(loss[pid], next(r["loss_usd"] for r in rec["scenario"]["positions"] if r["id"] == pid), pid)

    # Crosscheck all 80 quotes against original request/response, asset marks,
    # decimals RPC evidence, exact integer sizing, and actual cache timestamps.
    quote_count, quote_times, marks = 0, [], []
    for record in bundle["positions"].values():
        for asset in (record["input_asset"], record["output_asset"]):
            observed = labelled("fire_drill_asset:" + asset["address"])
            assert observed["meta"]["url"] == asset["metadata_url"]
            close(observed["data"]["price"]["usd"], asset["price_usd"], "asset mark", D("1e-10"))
            assert observed["data"]["priceUpdatedAt"] == asset["price_updated_at"]
            assert observed["data"]["decimals"] == asset["decimals"]
            rpc = labelled("fire_drill_decimals:" + asset["address"])
            assert rpc["data"] == asset["rpc_response"]
            assert key("POST", bundle["rpc"], body=asset["rpc_request"]) in RAW
            assert RAW[key("POST", bundle["rpc"], body=asset["rpc_request"])] == rpc
            assert int(rpc["data"]["result"], 16) == asset["decimals"]
            assert asset["rpc_request"]["params"][1] == bundle["rpc_block"]
            mark_time = datetime.fromisoformat(asset["price_updated_at"].replace("Z", "+00:00")).timestamp()
            assert mark_time <= observed["cached_at"] + 2
            marks.append({"asset": asset["address"], "price_updated_at": asset["price_updated_at"],
                          "retrieved_at": utc(observed["cached_at"])})
        inp, out = record["input_asset"], record["output_asset"]
        for q in record["options"]:
            if not q["available"]:
                continue
            raw = RAW[q["raw_cache_key"]]
            USED.add(q["raw_cache_key"])
            assert key("GET", q["url"], params=q["params"]) == q["raw_cache_key"]
            assert raw["meta"]["url"] == q["url"] and raw["meta"]["params"] == q["params"]
            assert raw["data"]["data"]["amountOut"] == q["amount_out"]
            assert raw["data"]["method"] == "swapExactPtForToken"
            assert raw["data"]["contractCallParams"][2] == q["amount_in"]
            assert raw["data"]["contractCallParams"][3]["tokenOut"].lower() == out["address"].lower()
            exact = int((D(q["notional_usd"]) / D(inp["price_usd"]) * D(10)**inp["decimals"]).to_integral_value(rounding=ROUND_DOWN))
            assert int(q["amount_in"]) == exact == int(q["params"]["amountIn"])
            value = D(q["amount_out"]) / D(10)**out["decimals"] * D(out["price_usd"])
            close(value, q["output_value_usd"], "raw quoted output")
            close(max(ZERO, D(q["notional_usd"]) - value), q["mark_shortfall_usd"], "shortfall")
            assert raw["cached_at"] <= datetime.fromisoformat(q["captured_at"]).timestamp() + 2
            quote_times.append(raw["cached_at"])
            quote_count += 1
    assert quote_count == 80

    # Reconstruct every candidate without importing exit_options.
    for p in book:
        pid, size = p["id"], D(p["size_usd"])
        candidates[pid] = [(ZERO, ZERO, ZERO, ZERO, ZERO)]
        for step in range(1, 21):
            f = D(step) / 20
            sold = size * f
            if p["kind"] == "pendle_pt":
                record = bundle["positions"][pid]
                q = next(o for o in record["options"] if D(o["fraction"]) == f)
                if not q["available"]:
                    continue
                out = record["output_asset"]
                value = D(q["amount_out"]) / D(10)**out["decimals"] * D(out["price_usd"])
                execution = max(ZERO, sold - value) + sold * D(".0002")
            else:
                if sold > sum(caps[pid].values()) + D(".001"):
                    continue
                execution = sold * D(".0002")
            conversion = sold * D(".001")
            carry = sold * apy[pid] * 30 / 365
            candidates[pid].append((f, sold, execution, conversion, carry))
            live = next(o for o in rec["exit_candidates"]["options"][pid] if D(o["fraction"]) == f)
            for field, value in zip(("notional_usd", "execution_usd", "conversion_usd", "carry_usd"),
                                    (sold, execution, conversion, carry)):
                close(value, live[field], "independent candidate " + field)
    selected = {a["id"]: next(o for o in candidates[a["id"]] if o[0] == D(a["fraction"]))
                for a in rec["plan"]["actions"]}
    original = sum(loss.values())
    avoided = sum(loss[pid] * o[0] for pid, o in selected.items())
    sold, execution, conversion, carry = [sum(o[i] for o in selected.values()) for i in range(1,5)]
    residual = original - avoided
    cost = execution + conversion + carry
    totals = {"loss_usd": original, "residual_loss_usd": residual,
              "execution_usd": execution, "conversion_usd": conversion, "carry_usd": carry,
              "protection_cost_usd": cost, "capital_sold_usd": sold,
              "capital_released_usd": sold - execution - conversion,
              "accounted_loss_usd": residual + execution + conversion,
              "avoided_loss_usd": avoided, "break_even_probability": cost / avoided}
    for name, value in totals.items():
        expected = rec["scenario"]["loss_usd"] if name == "loss_usd" else rec["plan"]["audit"][name]
        close(value, expected, name)

    # Audit the user's ORIGINAL four headlines too. Recreate the old 95% PT
    # rule and its original reductions using the same underlying observations.
    # This establishes arithmetic reproduction, not financial endorsement.
    old_fractions = {"pt-wsteth":D(".6"), "smokehouse-usdt":D(".8"),
                     "steakhouse-eth":D(1), "steakhouse-usdt":D(1)}
    old_choices = {pid:next(o for o in candidates[pid] if o[0]==old_fractions.get(pid,ZERO)) for pid in loss}
    old_loss = {pid:value * (D(".95") if pid=="pt-wsteth" else D(1)) for pid,value in loss.items()}
    old_residual = sum(old_loss[pid]*(1-o[0]) for pid,o in old_choices.items())
    old_sold, old_exec, old_conv, old_carry = [sum(o[i] for o in old_choices.values()) for i in range(1,5)]
    legacy = {"conditional_loss_usd":sum(old_loss.values()),
              "accounted_loss_usd":old_residual+old_exec+old_conv,
              "economic_protection_cost_usd":old_exec+old_conv+old_carry,
              "capital_released_usd":old_sold-old_exec-old_conv}
    for name, value in zip(legacy, (D("2311622.14"),D("498866.02"),D("21753.37"),D("3384390.70"))):
        close(legacy[name],value,"original headline "+name)

    by_vault, by_market = {}, {}
    for w in rec["plan"]["withdrawals"]:
        pid, mid, amount = w["position"], w["market"], D(w["amount_usd"])
        assert ZERO <= amount <= caps[pid][mid] + D(".02")
        by_vault[pid] = by_vault.get(pid, ZERO) + amount
        by_market[mid] = by_market.get(mid, ZERO) + amount
    for mid, amount in by_market.items():
        assert amount <= resources[mid] + D(".02")
    for pid in vaults:
        close(by_vault.get(pid, ZERO), selected[pid][1], "withdrawal funding")

    # Unaffected positions are dominated by holding (no avoided loss, positive
    # costs and capacity consumption). Enumerate the five affected positions.
    # Relaxing coupled liquidity gives a lower bound; the selected feasible plan
    # attains it, which proves optimality with capacities too.
    affected = sorted(pid for pid in loss if loss[pid] > 0)
    assert len(affected) == 5
    arrays = {}
    for pid in affected:
        arrays[pid] = np.array([[float(loss[pid] * o[0]), float(sum(o[2:])), float(o[2]+o[3])]
                               for o in candidates[pid]])
    front = list(itertools.product(*(range(len(arrays[p])) for p in affected[:3])))
    tail = np.array([arrays[affected[3]][i]+arrays[affected[4]][j]
                     for i,j in itertools.product(range(len(arrays[affected[3]])),range(len(arrays[affected[4]])))])
    minimum = float("inf")
    locked_min = float("inf")
    combinations = 0
    for inds in front:
        summed = tail + sum((arrays[p][i] for p,i in zip(affected[:3],inds)), start=np.zeros(3))
        accounted = float(original) - summed[:,0] + summed[:,2]
        eligible = accounted <= 500000 + .00001
        if eligible.any():
            minimum = min(minimum, float(summed[eligible,1].min()))
        if all(p != "pt-wsteth" or i == 0 for p,i in zip(affected[:3],inds)):
            # pt-wsteth happens to be in the first three sorted IDs; assert it.
            assert "pt-wsteth" in affected[:3]
            locked_min = min(locked_min, float(accounted.min()))
        combinations += len(tail)
    close(minimum, cost, "exhaustive global lower bound")
    assert locked_min > 500000

    times = [RAW[k]["cached_at"] for k in USED]
    assert max(times) <= datetime.now(timezone.utc).timestamp() + 2
    report = {"status": "PASS", "audited_at": datetime.now(timezone.utc).isoformat(),
        "method": "Independent Decimal raw-data reconstruction; no product financial imports; exhaustive grid enumeration",
        "superseded_original_headlines": {"totals":{k:float(v) for k,v in legacy.items()},
            "arithmetic":"PASS", "financial_review":"FAIL: unsupported 5% recovery on worthless PT underlying; corrected in v2"},
        "totals": {k:float(v) for k,v in totals.items()},
        "per_position_loss_usd": {k:float(v) for k,v in loss.items()}, "market_calculations": details,
        "actions": {pid:float(o[0]) for pid,o in selected.items() if o[0]},
        "enumerated_combinations": combinations, "relaxed_minimum_economic_cost_usd": minimum,
        "locked_minimum_lower_bound_usd": locked_min,
        "independently_verified_quotes": quote_count,
        "used_evidence_interval_utc": [utc(min(times)), utc(max(times))],
        "quote_retrieval_interval_utc": [utc(min(quote_times)), utc(max(quote_times))],
        "marks": marks,
        "economic_sensitivity": [{"assumed_probability": float(p), "expected_net_benefit_usd": float(p*avoided-cost)}
                                 for p in (D(0), D(".005"), D(".02"))],
        "economic_scope": "Least economic cost conditional on an explicit stress mandate; plan-versus-hold break-even, not an unconstrained expected-return optimum or estimated scenario probability",
        "source_hashes": {"data/raw/"+k+".json": hashlib.sha256((ROOT/"data/raw"/(k+".json")).read_text(encoding="utf-8").encode()).hexdigest() for k in sorted(USED)}}
    (ROOT / "artifacts/judge_independent_audit.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({"status":report["status"],"totals":report["totals"],
                      "combinations":combinations,"quotes":quote_count,
                      "evidence_interval":report["used_evidence_interval_utc"]},indent=2))


if __name__ == "__main__":
    main()
