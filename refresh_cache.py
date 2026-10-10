"""Single entry point to (re)build the on-disk API cache in data/raw/.

Run once with a network connection; afterwards the whole demo works offline
(set BLAST_RADIUS_OFFLINE=1 to prove it). Caches: the protocol catalog + hacks
dataset (risk models), the live venues for each configured position, and the
Stream Finance replay price series.

    python refresh_cache.py
"""
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from blast_radius.config import load_config  # noqa: E402
from blast_radius.sources import defillama, morpho, pendle  # noqa: E402
from blast_radius.sources.cache import cache_stats  # noqa: E402


def _unix(date_str: str) -> int:
    return int(dt.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp())


def _cache_pendle_pt(pos: dict) -> None:
    cid, market = pos["chain_id"], pos["market"]
    markets = pendle.markets_active(cid)["markets"]
    m = next((x for x in markets if x["address"].lower() == market.lower()), None)
    if not m:
        print(f"    ! market {market} not in active list"); return
    pendle.market_data(market, cid)
    pt_px = list(pendle.assets_prices([m["pt"]], cid)["prices"].values())[0]
    # Freeze a price-impact curve across exit sizes (used by exit_cost.py).
    for notional in (pos["size_usd"], pos["size_usd"] * 2, pos["size_usd"] * 10):
        wei = int((notional / pt_px) * 1e18)
        q = pendle.swap_quote(market, m["pt"], m["underlyingAsset"], wei, cid)
        pi = (q.get("data") or {}).get("priceImpact")
        print(f"    quote ${notional:,.0f} -> priceImpact {pi:+.4%}")


def _cache_morpho_vault(pos: dict) -> None:
    v = morpho.vault_by_address(pos["vault"], pos["chain_id"])
    n = len(v["state"]["allocation"]) if v else 0
    print(f"    vault {v['name'] if v else '?'} -> {n} allocations")


def main() -> None:
    cfg = load_config()
    print("Refreshing Blast Radius cache (data/raw/) ...")

    protos = defillama.protocols()
    print(f"  defillama /protocols            -> {len(protos)} protocols")
    hx = defillama.hacks()
    print(f"  defillama /hacks                -> {len(hx)} incidents")
    pm = pendle.markets_active(1)
    print(f"  pendle /v1/1/markets/active     -> {len(pm.get('markets', []))} markets")
    mv = morpho.vaults((1,), first=50)
    print(f"  morpho vaults (ethereum)        -> {len(mv)} vaults")

    print("  positions:")
    for pos in cfg.get("positions", []):
        print(f"    - {pos['label']} ({pos['kind']})")
        if pos["kind"] == "pendle_pt":
            _cache_pendle_pt(pos)
        elif pos["kind"] == "morpho_vault":
            _cache_morpho_vault(pos)

    rep = cfg.get("replay", {}).get("stream", {})
    if rep:
        start = _unix(rep["window"]["start"])
        span = rep["window"]["span"]
        for name, key in rep["coins"].items():
            series = defillama.chart(key, start=start, span=span, period="1d")
            n = len(((series.get("coins") or {}).get(key) or {}).get("prices", []))
            print(f"  replay price series {name:<7} ({key}) -> {n} points")

    print("Cache:", cache_stats())


if __name__ == "__main__":
    main()
