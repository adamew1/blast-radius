"""Read-only, additive capture of a small instrument catalog. No transactions.

Never overwrites the validated book, existing raw captures or execution bundle.
Catalog publication is contingent on separate independent and browser audits.
"""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from blast_radius.sources import pendle, morpho
from blast_radius.sources.cache import cached_get, cached_post, _key

RPC = "https://ethereum-rpc.publicnode.com"
PT_MARKETS = ("0xc5f938a8ef5f3bf9e72f5aa094baf5e03f4727d3", "0x4a5067c3ff1abb7449244025b0e37feaf77d8e3e")
VAULTS = ("0x31A5684983EeE865d943A696AAC155363bA024f9", "0xBEefb9f61CC44895d8AEc381373555a64191A9c4")


def stamp():
    return datetime.now(timezone.utc).isoformat()


def main():
    catalog_path = ROOT / "data/fire_drill/catalog.json"
    quote_path = ROOT / "data/fire_drill/catalog_execution.json"
    if catalog_path.exists() or quote_path.exists():
        raise SystemExit("Catalog capture already exists; review/version it explicitly rather than overwrite")
    markets = pendle.markets_active()["markets"]
    block_request = {"jsonrpc": "2.0", "id": 2, "method": "eth_blockNumber", "params": []}
    block = cached_post(RPC, block_request, label="catalog_rpc_block")["result"]
    header_request = {"jsonrpc": "2.0", "id": 2, "method": "eth_getBlockByNumber", "params": [block, False]}
    header = cached_post(RPC, header_request, label="catalog_rpc_header")["result"]
    catalog = {"schema": "blast-radius-catalog-v1", "captured_at": stamp(), "chain_id": 1, "positions": [],
               "classification": "bounded Ethereum catalog; frozen protocol API observations; no wallet import or universal support"}
    bundle = {"captured_at": stamp(), "rpc": RPC, "rpc_block": block, "rpc_block_timestamp": int(header["timestamp"], 16),
              "quote_method": "amountOut * output asset USD mark; fee already in output", "positions": {}}
    for address in PT_MARKETS:
        market = next(m for m in markets if m["address"].lower() == address)
        pid = "catalog-pt-" + address
        position = {"id": pid, "kind": "pendle_pt", "label": f"Pendle PT-{market['name']} · {market['expiry'][:10]}",
                    "chain": "ethereum", "chain_id": 1, "market": address, "size_usd": 1_000_000}
        pendle.market_data(address)  # own cached pool response; never borrow another market's state
        assets = []
        for value in (market["pt"], market["underlyingAsset"]):
            token = pendle._raw(value)
            url = f"{pendle.BASE}/v1/1/assets/{token}"
            asset = cached_get(url, label="catalog_asset:" + token)
            call = {"jsonrpc": "2.0", "id": 2, "method": "eth_call",
                    "params": [{"to": token, "data": "0x313ce567"}, block]}
            observed = cached_post(RPC, call, label="catalog_decimals:" + token)
            decimals = int(observed["result"], 16)
            if decimals != asset["decimals"] or asset["price"]["usd"] <= 0:
                raise ValueError("Invalid mark or inconsistent token decimals")
            assets.append({"address": token, "decimals": decimals, "symbol": asset["symbol"],
                           "price_usd": asset["price"]["usd"], "price_updated_at": asset.get("priceUpdatedAt"),
                           "metadata_url": url, "rpc_request": call, "rpc_response": observed})
        inp, out = assets
        options = []
        for step in range(1, 21):
            amount_usd = step * 50_000
            amount = int(Decimal(amount_usd) / Decimal(str(inp["price_usd"])) * 10**inp["decimals"])
            params = {"receiver": pendle.DEFAULT_RECEIVER, "slippage": .01,
                      "tokenIn": inp["address"], "tokenOut": out["address"], "amountIn": str(amount)}
            url = f"{pendle.BASE}/v2/sdk/1/markets/{address}/swap"
            try:
                response = cached_get(url, params=params, label=f"catalog_quote:{pid}:{step}")
                if response["method"] != "swapExactPtForToken":
                    raise ValueError("Unexpected quote method")
                amount_out = str(response["data"]["amountOut"])
                value = float(Decimal(amount_out) / 10**out["decimals"] * Decimal(str(out["price_usd"])))
                if value <= 0:
                    raise ValueError("Nonpositive quote output")
                options.append({"fraction": step/20, "notional_usd": amount_usd, "available": True,
                                "amount_in": str(amount), "amount_out": amount_out, "output_value_usd": value,
                                "mark_shortfall_usd": max(0, amount_usd-value), "signed_mark_shortfall_usd": amount_usd-value,
                                "url": url, "params": params, "raw_cache_key": _key("GET", url, params=params), "captured_at": stamp()})
            except Exception as error:
                options.append({"fraction": step/20, "notional_usd": amount_usd, "available": False,
                                "error": str(error)[:250], "captured_at": stamp()})
        if not any(o["available"] for o in options):
            raise ValueError(f"No supported quotes for {pid}")
        bundle["positions"][pid] = {"position": position, "input_asset": inp, "output_asset": out, "options": options}
        catalog["positions"].append(position)
        print(f"Captured {market['name']}: {sum(o['available'] for o in options)}/20 exact trades", flush=True)
    for address in VAULTS:
        vault = morpho.vault_by_address(address)
        if vault["address"].lower() != address.lower() or vault["chain"]["id"] != 1:
            raise ValueError("Vault identity/chain mismatch")
        state = vault["state"]
        for allocation in state["allocation"]:
            market = allocation["market"]
            if (allocation["supplyAssetsUsd"] and market["collateralAsset"] and
                    round(100*allocation["supplyAssetsUsd"]/state["totalAssetsUsd"], 2) >= .1):
                if any(market["state"].get(k) is None for k in ("supplyAssetsUsd", "borrowAssetsUsd", "collateralAssetsUsd")):
                    raise ValueError("Material funded market has incomplete balance sheet; exclude this vault")
        catalog["positions"].append({"id": "catalog-vault-" + address.lower(), "kind": "morpho_vault",
                                     "label": "Morpho " + vault["name"], "chain": "ethereum", "chain_id": 1,
                                     "vault": address, "size_usd": 1_000_000})
        print(f"Captured vault {vault['name']}: ${vault['state']['totalAssetsUsd']:,.0f} protocol assets", flush=True)
    bundle["completed_at"] = stamp()
    quote_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    catalog_path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    print("Saved separate catalog and execution captures; admission still requires validation", flush=True)


if __name__ == "__main__":
    main()
