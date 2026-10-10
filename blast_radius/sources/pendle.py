"""Pendle API v2 client (free, no key; 200/min, 200k/week). Verified paths only.

Gotchas (from probe): market data is on /v2/.../data (v1 is 404); the swap quote is on
/v2/sdk/.../swap (v1 is 404); `receiver` must be a valid EIP-55 address.
Token identifiers from the API are chainId-prefixed, e.g. "1-0xabc...".
"""
from __future__ import annotations

from .cache import cached_get

BASE = "https://api-v2.pendle.finance/core"
# A valid EIP-55 address, used only as the quote receiver (read-only, no tx sent).
DEFAULT_RECEIVER = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


def _raw(addr: str) -> str:
    """Strip Pendle's chainId prefix: '1-0xabc' -> '0xabc'."""
    return addr.split("-", 1)[1] if addr and "-" in addr else addr


def markets_active(chain_id: int = 1) -> dict:
    """Active markets. Each: name, address, pt, yt, sy, underlyingAsset, expiry,
    details.liquidity, details.impliedApy."""
    return cached_get(f"{BASE}/v1/{chain_id}/markets/active", label=f"pendle_active:{chain_id}")


def market_data(market: str, chain_id: int = 1) -> dict:
    """Pool state: liquidity.usd, totalTvl.usd, totalPt, totalSy, impliedApy, ptDiscount, assetPriceUsd."""
    return cached_get(f"{BASE}/v2/{chain_id}/markets/{market}/data", label=f"pendle_data:{market}")


def assets_prices(addresses: list[str], chain_id: int = 1) -> dict:
    addrs = ",".join(_raw(a) for a in addresses)
    return cached_get(
        f"{BASE}/v1/{chain_id}/assets/prices", params={"addresses": addrs}, label="pendle_prices"
    )


def swap_quote(
    market: str,
    token_in: str,
    token_out: str,
    amount_in_wei: int,
    chain_id: int = 1,
    slippage: float = 0.01,
    receiver: str = DEFAULT_RECEIVER,
) -> dict:
    """Exit quote -> data.priceImpact + data.amountOut. Vary amount_in_wei for the slippage curve.
    For a PT exit: token_in = PT address, token_out = underlying address."""
    params = {
        "receiver": receiver,
        "slippage": slippage,
        "tokenIn": _raw(token_in),
        "tokenOut": _raw(token_out),
        "amountIn": str(int(amount_in_wei)),
    }
    return cached_get(
        f"{BASE}/v2/sdk/{chain_id}/markets/{market}/swap",
        params=params,
        label=f"pendle_swap:{market}:{amount_in_wei}",
    )
