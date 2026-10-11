"""Independent modified-book audit. No imports from blast_radius or its solver.

Raw API data and Decimal arithmetic reconstruct stress, exact-amount exit costs,
funded claims and shared liquidity. Exhaustive relaxed enumeration proves the
objective when the independently resource-verified plan attains that bound.
"""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = lambda value: Decimal(str(value))
ZERO = D(0)
WSTETH = "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0"


def close(actual, expected, reason, tolerance=D(".02")):
    assert abs(D(actual) - D(expected)) <= tolerance, (reason, actual, expected)


def audit(path):
    rec = json.loads(path.read_text(encoding="utf-8"))
    assert rec["receipt_schema"] in ("blast-radius-decision-v2", "blast-radius-decision-v3")
    for name, digest in rec["evidence"]["files"].items():
        assert hashlib.sha256((ROOT / name).read_text(encoding="utf-8").encode()).hexdigest() == digest
    for source in rec["evidence"]["sources"]:
        assert hashlib.sha256((ROOT / source["path"]).read_text(encoding="utf-8").encode()).hexdigest() == source["sha256"]
    raw = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "data/raw").glob("*.json")}

    def labelled(label):
        matches = [v for v in raw.values() if v["meta"].get("label") == label]
        assert len(matches) == 1, label
        return matches[0]["data"]

    supported = {p["id"]: p for p in json.loads((ROOT / "data/book/sample_book.json").read_text())["positions"]}
    bundle = json.loads((ROOT / "data/fire_drill/execution.json").read_text())
    if rec["receipt_schema"] == "blast-radius-decision-v3":
        supported.update({p["id"]: p for p in json.loads((ROOT / "data/fire_drill/catalog.json").read_text())["positions"]})
        if any(p["kind"] == "pendle_pt" and p["id"] not in bundle["positions"] for p in rec["portfolio"]):
            extra = json.loads((ROOT / "data/fire_drill/catalog_execution.json").read_text())
            bundle["positions"].update(extra["positions"])
            bundle["catalog_rpc"] = {k: extra[k] for k in ("rpc", "rpc_block", "rpc_block_timestamp")}
    assert rec["quote_bundle"] == bundle
    markets = {m["address"].lower(): m for m in labelled("pendle_active:1")["markets"]}
    pt_index = {m["pt"].split("-", 1)[-1].lower(): m for m in markets.values()}

    target = rec["scenario"]["dependency_id"].removeprefix("token:ethereum:")
    assert rec["scenario"]["dependency_id"].startswith("token:ethereum:")

    def shock(address):
        address = address.lower()
        if address == target:
            return D(1)
        if address in pt_index:
            return shock(pt_index[address]["underlyingAsset"].split("-", 1)[-1])
        return ZERO

    assert rec["scenario"]["severity"] == 1
    losses, choices, caps, capacities = {}, {}, {}, {}
    assert len({p["id"] for p in rec["portfolio"]}) == len(rec["portfolio"])
    for p in rec["portfolio"]:
        pid, size = p["id"], D(p["size_usd"])
        assert {k: v for k, v in p.items() if k != "size_usd"} == {k: v for k, v in supported[pid].items() if k != "size_usd"}
        assert 0 < size <= 2_000_000 and size % 50_000 == 0
        if p["kind"] == "pendle_pt":
            market = markets[p["market"].lower()]
            losses[pid] = size * shock(market["underlyingAsset"].split("-", 1)[-1])
            apy = max(ZERO, D(market["details"].get("impliedApy") or 0))
        else:
            vault = labelled("morpho_vault:" + p["vault"])
            assert vault["data"]["vaultByAddress"]["address"].lower() == p["vault"].lower()
            state = vault["data"]["vaultByAddress"]["state"]
            total = D(state["totalAssetsUsd"])
            apy = max(ZERO, D(state["netApy"] if state["netApy"] is not None else state["apy"]))
            caps[pid], losses[pid] = {}, ZERO
            for allocation in state["allocation"]:
                market, funded = allocation["market"], D(allocation["supplyAssetsUsd"] or 0)
                balance = market["state"]
                mid, liquid = market["marketId"], balance["liquidityAssetsUsd"]
                if funded > 0 and liquid is not None:
                    cap = max(ZERO, D(liquid))
                    capacities[mid] = min(capacities.get(mid, cap), cap)
                    caps[pid][mid] = caps[pid].get(mid, ZERO) + min(funded, cap)
                collateral = market["collateralAsset"]
                if not collateral or funded <= 0 or round(float(100 * funded / total), 2) < .1:
                    continue
                hit = shock(collateral["address"])
                if hit:
                    supply, debt, backing = (D(balance[k]) for k in ("supplyAssetsUsd", "borrowAssetsUsd", "collateralAssetsUsd"))
                    impairment = min(D(1), max(ZERO, (max(ZERO, debt - backing * (1-hit)) - max(ZERO, debt-backing)) / supply))
                    losses[pid] += size * funded / total * impairment
        close(next(r["loss_usd"] for r in rec["scenario"]["positions"] if r["id"] == pid), losses[pid], "position loss")
        # Tuple: exit fraction, exact dollar amount, execution, conversion, carry.
        choices[pid] = [(ZERO, ZERO, ZERO, ZERO, ZERO, "hold")]
        if p["kind"] == "pendle_pt":
            record = bundle["positions"][pid]
            out = record["output_asset"]
            for quote in record["options"]:
                amount = D(quote["notional_usd"])
                if not quote["available"] or amount > size:
                    continue
                response = raw[quote["raw_cache_key"]]
                assert response["meta"]["params"] == quote["params"]
                assert response["data"]["data"]["amountOut"] == quote["amount_out"]
                assert response["data"]["contractCallParams"][2] == quote["amount_in"]
                assert int(out["rpc_response"]["result"], 16) == out["decimals"]
                value = D(quote["amount_out"]) / D(10)**out["decimals"] * D(out["price_usd"])
                execution = max(ZERO, amount - value) + amount * D(".0002")
                choices[pid].append((amount/size, amount, execution, amount*D(".001"), amount*apy*30/365, quote["raw_cache_key"]))
        else:
            for step in range(1, 21):
                fraction = D(step)/20
                amount = size * fraction
                if amount <= sum(caps[pid].values()) + D(".001"):
                    choices[pid].append((fraction, amount, amount*D(".0002"), amount*D(".001"), amount*apy*30/365,
                                         "cached Morpho funded allocations and market liquidity"))
        emitted = rec["exit_candidates"]["options"][pid]
        assert len(emitted) == len(choices[pid])
        for actual, expected in zip(emitted, choices[pid]):
            for field, value in zip(("fraction", "notional_usd", "execution_usd", "conversion_usd", "carry_usd"), expected):
                close(actual[field], value, "candidate " + field, D("1e-12") if field == "fraction" else D(".02"))
            assert actual["source"] == expected[5]

    assert set(rec["exit_candidates"]["options"]) == set(choices)
    assert rec["exit_candidates"]["resources"] == {mid: float(value) for mid, value in capacities.items()}
    assert rec["exit_candidates"]["vault_caps"] == {
        pid: {mid: float(value) for mid, value in values.items()} for pid, values in caps.items()}
    plan = rec["plan"]
    assert not plan["locks"]
    selected = {}
    for action in plan["actions"]:
        assert action["id"] not in selected
        option = next(o for o in choices[action["id"]] if o[1] == D(action["notional_usd"]))
        for field, value in zip(("fraction", "notional_usd", "execution_usd", "conversion_usd", "carry_usd"), option):
            close(action[field], value, "selected " + field)
        selected[action["id"]] = option
    assert set(selected) == set(choices)
    by_market, by_vault, seen = {}, {}, set()
    for withdrawal in plan["withdrawals"]:
        pid, mid, amount = withdrawal["position"], withdrawal["market"], D(withdrawal["amount_usd"])
        assert (pid, mid) not in seen
        seen.add((pid, mid))
        assert ZERO <= amount <= caps[pid][mid] + D(".02")
        by_market[mid] = by_market.get(mid, ZERO) + amount
        by_vault[pid] = by_vault.get(pid, ZERO) + amount
    for mid, amount in by_market.items():
        assert amount <= capacities[mid] + D(".02")
    for pid in caps:
        close(by_vault.get(pid, ZERO), selected[pid][1], "withdrawal funding")
    original = sum(losses.values())
    residual = original - sum(losses[pid]*o[0] for pid, o in selected.items())
    sold, execution, conversion, carry = (sum(o[i] for o in selected.values()) for i in range(1, 5))
    accounted, cost = residual + execution + conversion, execution + conversion + carry
    close(original, rec["scenario"]["loss_usd"], "total loss")
    close(sum(D(p["size_usd"]) for p in rec["portfolio"]), rec["scenario"]["aum_usd"], "AUM")
    for key, value in {"residual_loss_usd": residual, "capital_sold_usd": sold, "execution_usd": execution,
                       "conversion_usd": conversion, "carry_usd": carry, "accounted_loss_usd": accounted,
                       "capital_released_usd": sold-execution-conversion, "protection_cost_usd": cost}.items():
        close(value, plan["audit"][key], key)

    affected = [pid for pid in choices if losses[pid] > 0]
    minimum, least_cost, enumerated = None, None, 0
    for combination in itertools.product(*(choices[pid] for pid in affected)):
        enumerated += 1
        loss = original - sum(losses[pid]*o[0] for pid, o in zip(affected, combination)) + sum(o[2]+o[3] for o in combination)
        economic = sum(o[2]+o[3]+o[4] for o in combination)
        minimum = loss if minimum is None else min(minimum, loss)
        if loss <= D(plan["loss_limit_usd"]):
            least_cost = economic if least_cost is None else min(least_cost, economic)
    if least_cost is None:
        assert plan["status"] == "infeasible" and not plan["target_met"] and plan["minimum_attainable_proved"]
        close(accounted, minimum, "minimum-loss optimum")
    else:
        assert plan["status"] == "optimal" and plan["target_met"] and accounted <= D(plan["loss_limit_usd"]) + D(".02")
        close(cost, least_cost, "least-cost optimum")
    return {"receipt": str(path.relative_to(ROOT)).replace("\\", "/"), "positions": len(choices),
            "aum_usd": rec["scenario"]["aum_usd"], "loss_usd": float(original),
            "status": plan["status"], "accounted_loss_usd": float(accounted), "protection_cost_usd": float(cost),
            "combinations_enumerated": enumerated, "independent_optimality_proved": True,
            "funded_claims_and_shared_liquidity_verified": True}


def main():
    results = [audit(ROOT / f"artifacts/challenge_{name}_receipt.json") for name in ("resized", "removed", "quote_bound")]
    report = {"status": "passed", "verified_at": datetime.now(timezone.utc).isoformat(),
              "method": "Raw protocol responses and Decimal arithmetic; exhaustive relaxed enumeration attained by independently resource-verified plans; no financial engine or solver imports",
              "cases": results}
    (ROOT / "artifacts/challenge_independent_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    for result in results:
        print(f"PASS {result['receipt']}: {result['status']}; {result['combinations_enumerated']:,} combinations independently enumerated")


if __name__ == "__main__":
    main()
