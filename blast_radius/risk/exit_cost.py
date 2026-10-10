"""Real exit-cost estimation.

Pendle PT: the Pendle SDK swap quote returns a genuine `priceImpact` for unwinding the exact
position size back to the underlying; exit cost = |priceImpact| + the pool fee. We also build
a price-impact curve across sizes so the UI can show how exit cost grows with size.

Morpho vault: the supplier exits by withdrawing the loan asset, which is bounded by the
vault's currently-available liquidity (sum of per-market `liquidityAssetsUsd`). Within that,
exit is ~gas; a shortfall must wait for borrowers to repay or be force-sold, which we charge
as an illiquidity penalty.
"""
from __future__ import annotations

from ..sources import morpho, pendle

_GAS_BPS = 0.0002            # ~2bps round-trip gas/slippage floor
_ILLIQUIDITY_PENALTY = 0.02  # 2% haircut on the portion that exceeds available liquidity


def exit_cost(position: dict) -> dict:
    if position["kind"] == "pendle_pt":
        return _pendle_exit(position)
    if position["kind"] == "morpho_vault":
        return _morpho_exit(position)
    return {"cost_pct": _GAS_BPS, "method": "unknown", "detail": "default gas floor"}


def _pendle_exit(position: dict) -> dict:
    cid, market = position.get("chain_id", 1), position["market"]
    m = next((x for x in pendle.markets_active(cid)["markets"]
              if x["address"].lower() == market.lower()), None)
    if not m:
        return {"cost_pct": _GAS_BPS, "method": "pendle", "detail": "market not found"}
    fee = (m.get("details") or {}).get("feeRate") or 0.0
    pt_px = list(pendle.assets_prices([m["pt"]], cid)["prices"].values())[0]
    size = position.get("size_usd", 0)

    def quote(notional: float) -> float | None:
        wei = int((notional / pt_px) * 1e18)
        try:
            q = pendle.swap_quote(market, m["pt"], m["underlyingAsset"], wei, cid)
        except Exception:
            return None  # size exceeds pool liquidity / router can't fill -> no quote
        return (q.get("data") or {}).get("priceImpact")

    pi = quote(size)
    curve = []
    for mult in (0.5, 1, 2, 5, 10):
        p = quote(size * mult)
        if p is not None:
            curve.append({"size_usd": size * mult, "price_impact": abs(p), "cost_pct": abs(p) + fee})
    if pi is None:
        # position itself exceeds available liquidity: exit cost is at least the deepest quote,
        # bumped for the unfillable remainder.
        deepest = max((c["cost_pct"] for c in curve), default=0.03)
        return {"cost_pct": max(deepest, 0.03), "price_impact": None, "fee": fee,
                "method": "pendle price-impact",
                "detail": f"${size:,.0f} exceeds instantly-routable liquidity; exit is illiquid",
                "curve": curve, "pt_price": pt_px}
    cost = abs(pi) + fee
    return {"cost_pct": cost, "price_impact": abs(pi), "fee": fee, "method": "pendle price-impact",
            "detail": f"Pendle SDK swap quote at ${size:,.0f}", "curve": curve, "pt_price": pt_px}


def _morpho_exit(position: dict) -> dict:
    v = morpho.vault_by_address(position["vault"], position.get("chain_id", 1))
    size = position.get("size_usd", 0)
    withdrawable = 0.0
    for a in ((v.get("state") or {}).get("allocation") or []):
        withdrawable += ((a.get("market") or {}).get("state") or {}).get("liquidityAssetsUsd") or 0.0
    if size <= withdrawable:
        return {"cost_pct": _GAS_BPS, "method": "morpho withdrawable liquidity",
                "detail": f"${withdrawable:,.0f} instantly withdrawable ≥ ${size:,.0f} position",
                "withdrawable_usd": withdrawable}
    shortfall = (size - withdrawable) / size
    cost = _GAS_BPS + shortfall * _ILLIQUIDITY_PENALTY
    return {"cost_pct": cost, "method": "morpho withdrawable liquidity",
            "detail": f"only ${withdrawable:,.0f} of ${size:,.0f} instantly withdrawable; "
                      f"{shortfall:.0%} waits for repayment (≈{_ILLIQUIDITY_PENALTY:.0%} haircut)",
            "withdrawable_usd": withdrawable}
