"""Research costs from audited frozen evidence; unavailable sizes never imply fills."""
from __future__ import annotations

from ..fire_drill.execution import load_execution
from ..sources import morpho

_GAS_RESERVE = .0002
_CONVERSION_RESERVE = .001


def unavailable(method, detail):
    return {"cost_pct": 0.0, "available": False, "method": method, "detail": detail,
            "curve": []}  # placeholder never used to issue a decision


def exit_cost(position: dict) -> dict:
    if position["kind"] == "pendle_pt":
        return _pendle_exit(position)
    if position["kind"] == "morpho_vault":
        return _morpho_exit(position)
    return unavailable("unsupported", "No supported execution evidence")


def _pendle_exit(position: dict) -> dict:
    record = next((r for r in load_execution()["positions"].values()
                   if r["position"]["market"].lower() == position["market"].lower()
                   and r["position"]["chain_id"] == position.get("chain_id", 1)), None)
    if record is None:
        return unavailable("frozen Pendle quotes", "No captured market quotes")
    size = position.get("size_usd", 0)
    valid = [q for q in record["options"] if q["available"]]
    q = next((q for q in valid if abs(q["notional_usd"] - size) < .01), None)
    if q is None or size <= 0:
        return unavailable("frozen Pendle quotes", "No captured quote for this exact size; no extrapolated fill")
    reserve = _GAS_RESERVE + _CONVERSION_RESERVE
    return {"available": True, "cost_pct": q["mark_shortfall_usd"] / size + reserve,
            "price_impact": abs(q["reported_price_impact"]), "fee": 0.0,
            "method": "frozen quoted output + assumed gas/conversion reserves",
            "detail": "Captured amountOut valued once; reported pool fee already included. "
                      "Conversion to external cash is assumed, not quoted. No future fill guarantee.",
            "curve": [{"size_usd": v["notional_usd"], "price_impact": abs(v["reported_price_impact"]),
                       "cost_pct": v["mark_shortfall_usd"] / v["notional_usd"] + reserve} for v in valid],
            "pt_price": record["input_asset"]["price_usd"], "raw_cache_key": q["raw_cache_key"]}


def _morpho_exit(position: dict) -> dict:
    v = morpho.vault_by_address(position["vault"], position.get("chain_id", 1))
    size = position.get("size_usd", 0)
    withdrawable = sum(min(a.get("supplyAssetsUsd") or 0,
                          max(0, ((a.get("market") or {}).get("state") or {}).get("liquidityAssetsUsd") or 0))
                       for a in (v.get("state") or {}).get("allocation", []))
    if size > withdrawable or size <= 0:
        return {**unavailable("Morpho snapshot bound", "Exact exit exceeds funded snapshot liquidity; no assumed fill"),
                "withdrawable_usd": withdrawable}
    return {"available": True, "cost_pct": _GAS_RESERVE + _CONVERSION_RESERVE,
            "method": "Morpho funded snapshot liquidity + assumed reserves",
            "detail": f"${withdrawable:,.0f} funded liquidity bound; withdrawal queue not certified. "
                      "2 bps gas and 10 bps external-cash conversion are assumptions.",
            "withdrawable_usd": withdrawable}
