"""Capture real candidate quotes and RPC decimals; run once with network access.

No transactions are submitted. Runtime reads the resulting immutable bundle.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import time
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from blast_radius.portfolio.book import load_book
from blast_radius.sources import pendle
from blast_radius.sources.cache import cached_get, cached_post, _key, _path

RPC = "https://ethereum-rpc.publicnode.com"
RATE_LOCK = threading.Lock()
LAST_REQUEST = 0.0


def paced_get(url, **kwargs):
    global LAST_REQUEST
    if _path(_key("GET", url, params=kwargs.get("params"))).exists():
        return cached_get(url, **kwargs)
    for attempt in range(4):
        with RATE_LOCK:
            time.sleep(max(0, 1.1 - (time.monotonic() - LAST_REQUEST)))
            LAST_REQUEST = time.monotonic()
        try:
            return cached_get(url, **kwargs)
        except Exception as e:
            if "429" not in str(e) or attempt == 3:
                raise
            time.sleep(10 * (attempt + 1))


def stamp():
    return datetime.now(timezone.utc).isoformat()


def main():
    out = ROOT / "data/fire_drill/execution.json"
    out.parent.mkdir(exist_ok=True)
    book = load_book()["positions"]
    markets = pendle.markets_active()["markets"]
    block_request = {"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []}
    block = cached_post(RPC, block_request, label="fire_drill_rpc_block")["result"]
    bundle = {"captured_at": stamp(), "rpc": RPC, "rpc_block": block,
              "quote_method": "amountOut * output asset USD mark; fee already in output",
              "gas_bps_assumed": 2, "conversion_bps_assumed": 10, "positions": {}}
    for p in book:
        if p["kind"] != "pendle_pt":
            continue
        m = next(m for m in markets if m["address"].lower() == p["market"].lower())
        assets = []
        for addr in (m["pt"], m["underlyingAsset"]):
            addr = pendle._raw(addr)
            url = f"{pendle.BASE}/v1/1/assets/{addr}"
            asset = paced_get(url, label=f"fire_drill_asset:{addr}")
            call = {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                    "params": [{"to": addr, "data": "0x313ce567"}, block]}
            raw_decimals = cached_post(RPC, call, label=f"fire_drill_decimals:{addr}")
            decimals = int(raw_decimals["result"], 16)
            if decimals != asset["decimals"]:
                raise ValueError(f"API/RPC decimals disagree: {addr}")
            assets.append({"address": addr, "decimals": decimals, "symbol": asset["symbol"],
                           "price_usd": asset["price"]["usd"], "price_updated_at": asset.get("priceUpdatedAt"),
                           "metadata_url": url, "rpc_request": call, "rpc_response": raw_decimals})
        inp, output = assets
        print(f"Capturing {p['id']} ({inp['decimals']}/{output['decimals']} decimals)", flush=True)

        def capture(step):
            fraction = step / 20
            notional = p["size_usd"] * fraction
            amount = int(Decimal(str(notional)) / Decimal(str(inp["price_usd"])) * 10 ** inp["decimals"])
            try:
                params = {"receiver": pendle.DEFAULT_RECEIVER, "slippage": 0.01,
                          "tokenIn": inp["address"], "tokenOut": output["address"], "amountIn": str(amount)}
                url = f"{pendle.BASE}/v2/sdk/1/markets/{p['market']}/swap"
                q = paced_get(url, params=params, label=f"fire_drill_quote:{p['id']}:{step}")
                data = q["data"]
                amount_out = str(data["amountOut"])
                output_value = float(Decimal(amount_out) / 10 ** output["decimals"] * Decimal(str(output["price_usd"])))
                if output_value <= 0:
                    raise ValueError("Nonpositive quoted output")
                params = {"receiver": pendle.DEFAULT_RECEIVER, "slippage": 0.01,
                          "tokenIn": inp["address"], "tokenOut": output["address"], "amountIn": str(amount)}
                url = f"{pendle.BASE}/v2/sdk/1/markets/{p['market']}/swap"
                return {"fraction": fraction, "notional_usd": notional, "available": True,
                        "amount_in": str(amount), "amount_out": amount_out,
                        "output_value_usd": output_value,
                        "mark_shortfall_usd": max(0, notional - output_value),
                        "signed_mark_shortfall_usd": notional - output_value,
                        "reported_price_impact": data.get("priceImpact"), "reported_fee": data.get("fee"),
                        "url": url, "params": params, "raw_cache_key": _key("GET", url, params=params),
                        "captured_at": stamp()}
            except Exception as e:
                return {"fraction": fraction, "notional_usd": notional, "available": False,
                        "error": str(e)[:350], "captured_at": stamp()}

        with ThreadPoolExecutor(max_workers=3) as pool:
            options = list(pool.map(capture, range(1, 21)))
        bundle["positions"][p["id"]] = {"position": p, "input_asset": inp,
                                              "output_asset": output, "options": options}
        out.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
        print(f"  {sum(o['available'] for o in options)}/20 available", flush=True)
        time.sleep(0.5)
    bundle["completed_at"] = stamp()
    out.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    print(f"Saved {out} SHA256 {hashlib.sha256(out.read_bytes()).hexdigest()}", flush=True)


if __name__ == "__main__":
    main()
