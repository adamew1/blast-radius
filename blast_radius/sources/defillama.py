"""DefiLlama client (free, no key). Verified endpoints only (see plan/probe).

Reliable in /protocols: name, slug, category, chains, tvl, parentProtocol, audits, listedAt.
NOT reliable: `oracles`, `forkedFrom` (near-empty) -> oracle info comes from Morpho / manual map.
"""
from __future__ import annotations

from typing import Optional

from .cache import cached_get

API = "https://api.llama.fi"
COINS = "https://coins.llama.fi"


def protocols() -> list[dict]:
    """Full protocol catalog (~8700 rows)."""
    return cached_get(f"{API}/protocols", label="protocols")


def protocol(slug: str) -> dict:
    """Protocol detail: TVL time-series by chain, token breakdowns, embedded raises, hallmarks."""
    return cached_get(f"{API}/protocol/{slug}", label=f"protocol:{slug}")


def hacks() -> list[dict]:
    """Hacks dataset (~1300 incidents). Fields: date, amount, classification, technique,
    chain (array), targetType, defillamaId (nullable)."""
    return cached_get(f"{API}/hacks", label="hacks")


def prices_current(coins: list[str], search_width: str = "4h") -> dict:
    key = ",".join(coins)
    return cached_get(
        f"{COINS}/prices/current/{key}",
        params={"searchWidth": search_width},
        label=f"price_current:{key}",
    )


def prices_historical(timestamp: int, coins: list[str]) -> dict:
    key = ",".join(coins)
    return cached_get(
        f"{COINS}/prices/historical/{timestamp}/{key}", label=f"price_hist:{timestamp}"
    )


def chart(
    coins, start: int, span: int = 30, period: str = "1d", end: Optional[int] = None
) -> dict:
    """Daily price series. `coins` is one key or a list of keys (coingecko:<id> or <chain>:<addr>)."""
    if isinstance(coins, (list, tuple)):
        coins = ",".join(coins)
    params = {"start": start, "span": span, "period": period}
    if end:
        params["end"] = end
    return cached_get(f"{COINS}/chart/{coins}", params=params, label=f"chart:{coins}")
