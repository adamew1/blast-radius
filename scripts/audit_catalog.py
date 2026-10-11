"""Independent evidence and optimality audit for the additional instruments.

No imports from blast_radius or SciPy. Reuses the independent Decimal enumerator.
"""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_portfolio_challenge import audit, close

D = lambda value: Decimal(str(value))


def main():
    raw = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "data/raw").glob("*.json")}
    catalog = json.loads((ROOT / "data/fire_drill/catalog.json").read_text())
    bundle = json.loads((ROOT / "data/fire_drill/catalog_execution.json").read_text())
    original = json.loads((ROOT / "data/book/sample_book.json").read_text())["positions"]
    assert not ({p["id"] for p in original} & {p["id"] for p in catalog["positions"]})

    def response(method, url, params=None, body=None):
        key = hashlib.sha256(json.dumps({"m": method, "u": url, "p": params, "b": body}, sort_keys=True).encode()).hexdigest()[:20]
        record = raw[key]
        assert record["meta"]["url"] == url
        if method == "GET":
            assert record["meta"]["params"] == params
        # POST cache identity hashes the complete request body; the existing
        # raw-cache format stores method/URL but does not repeat that body.
        assert record["meta"]["method"] == method
        return record

    active = next(d for d in raw.values() if d["meta"].get("label") == "pendle_active:1")["data"]["markets"]
    markets = {m["address"].lower(): m for m in active}
    header = response("POST", bundle["rpc"], body={"jsonrpc": "2.0", "id": 2, "method": "eth_getBlockByNumber",
                                                              "params": [bundle["rpc_block"], False]})["data"]["result"]
    assert int(header["timestamp"], 16) == bundle["rpc_block_timestamp"]
    quotes, times, observed = 0, [], []
    for p in catalog["positions"]:
        if p["kind"] == "pendle_pt":
            record = bundle["positions"][p["id"]]
            assert record["position"] == p
            market = markets[p["market"].lower()]
            for field, address in (("input_asset", market["pt"].split("-", 1)[-1]),
                                   ("output_asset", market["underlyingAsset"].split("-", 1)[-1])):
                asset = record[field]
                assert asset["address"].lower() == address.lower()
                api = response("GET", asset["metadata_url"])
                assert api["data"]["decimals"] == asset["decimals"]
                assert api["data"]["priceUpdatedAt"] == asset["price_updated_at"]
                assert api["data"]["price"]["usd"] == asset["price_usd"]
                rpc = response("POST", bundle["rpc"], body=asset["rpc_request"])
                assert rpc["data"] == asset["rpc_response"]
                assert int(rpc["data"]["result"], 16) == asset["decimals"]
                assert asset["rpc_request"]["params"] == [{"to": asset["address"], "data": "0x313ce567"}, bundle["rpc_block"]]
                times += [api["cached_at"], rpc["cached_at"]]
            inp, out = record["input_asset"], record["output_asset"]
            for quote in record["options"]:
                if not quote["available"]:
                    continue
                q = response("GET", quote["url"], params=quote["params"])
                assert f"/markets/{p['market']}/swap" in quote["url"]
                assert q["data"]["method"] == "swapExactPtForToken"
                assert q["data"]["contractCallParams"][1].lower() == p["market"].lower()
                assert q["data"]["contractCallParams"][2] == quote["amount_in"] == quote["params"]["amountIn"]
                assert q["data"]["contractCallParams"][3]["tokenOut"].lower() == out["address"].lower()
                assert q["data"]["data"]["amountOut"] == quote["amount_out"]
                expected = int((D(quote["notional_usd"])/D(inp["price_usd"])*D(10)**inp["decimals"]).to_integral_value(rounding=ROUND_DOWN))
                assert int(quote["amount_in"]) == expected
                value = D(quote["amount_out"])/D(10)**out["decimals"]*D(out["price_usd"])
                close(value, quote["output_value_usd"], "quoted output valuation")
                close(max(D(0), D(quote["notional_usd"])-value), quote["mark_shortfall_usd"], "execution shortfall")
                quotes += 1
                times.append(q["cached_at"])
            observed.append({"id": p["id"], "label": p["label"], "own_snapshot_apy": market["details"]["impliedApy"],
                             "quotes": sum(q["available"] for q in record["options"]), "max_captured_trade_usd": max(q["notional_usd"] for q in record["options"] if q["available"])})
        else:
            candidates = [d for d in raw.values() if d["meta"].get("label") == "morpho_vault:" + p["vault"]]
            assert len(candidates) == 1
            packet = candidates[0]
            vault = packet["data"]["data"]["vaultByAddress"]
            assert vault["address"].lower() == p["vault"].lower() and vault["chain"]["id"] == 1
            state = vault["state"]
            for allocation in state["allocation"]:
                m = allocation["market"]
                if allocation["supplyAssetsUsd"] and m["collateralAsset"] and round(100*allocation["supplyAssetsUsd"]/state["totalAssetsUsd"], 2) >= .1:
                    assert all(m["state"][k] is not None and D(m["state"][k]) >= 0 for k in ("supplyAssetsUsd", "borrowAssetsUsd", "collateralAssetsUsd"))
                if allocation["supplyAssetsUsd"] > 0:
                    assert m["state"]["liquidityAssetsUsd"] is not None
            times.append(packet["cached_at"])
            observed.append({"id": p["id"], "label": p["label"], "own_snapshot_apy": state["netApy"],
                             "protocol_assets_usd": state["totalAssetsUsd"], "funded_allocation_records": len(state["allocation"])})
    assert quotes == 40
    decisions = [audit(ROOT / f"artifacts/catalog_{name}_receipt.json") for name in ("wsteth", "apyusd", "usd3")]
    report = {"status": "passed", "verified_at": datetime.now(timezone.utc).isoformat(),
              "method": "Raw request/response identity, RPC decimals, own asset marks, exact integer quote amounts, funded lending balance sheets; independent Decimal stress and exhaustive optimality verification without financial engine imports",
              "additional_instruments": observed, "quotes_verified": quotes,
              "new_evidence_retrieval_window_utc": [datetime.fromtimestamp(t, timezone.utc).isoformat() for t in (min(times), max(times))],
              "rpc_block": bundle["rpc_block"], "rpc_block_timestamp": bundle["rpc_block_timestamp"],
              "cases": decisions, "excluded": catalog.get("excluded", [])}
    (ROOT / "artifacts/catalog_independent_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"PASS {len(observed)} new instruments, {quotes} quotes, three all-new-book decisions independently verified")
    for case in decisions:
        print(f"PASS {case['receipt']}: {case['status']}; ${case['accounted_loss_usd']:,.2f} accounted loss; {case['combinations_enumerated']} combinations")


if __name__ == "__main__":
    main()
