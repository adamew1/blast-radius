"""Single entry point to (re)build the on-disk API cache in data/raw/.

Run once with a network connection; afterwards the whole demo works offline.
Expanded in Phase 1 to pull the exact demo positions + Stream replay series.

    python refresh_cache.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from blast_radius.sources import defillama, morpho, pendle  # noqa: E402
from blast_radius.sources.cache import cache_stats  # noqa: E402


def main() -> None:
    print("Refreshing Blast Radius cache (data/raw/) ...")
    # Catalog + incident dataset (used by the risk models).
    protos = defillama.protocols()
    print(f"  defillama /protocols            -> {len(protos)} protocols")
    hx = defillama.hacks()
    print(f"  defillama /hacks                -> {len(hx)} incidents")
    # Live venues for the demo positions (details filled in Phase 1).
    pm = pendle.markets_active(1)
    n = len(pm.get("markets", [])) if isinstance(pm, dict) else 0
    print(f"  pendle /v1/1/markets/active     -> {n} markets")
    mv = morpho.vaults((1,), first=50)
    print(f"  morpho vaults (ethereum)        -> {len(mv)} vaults")
    print("Cache:", cache_stats())


if __name__ == "__main__":
    main()
