"""Loss pass-through: how much of a shock at a child node reaches its parent.

A directed edge (parent -> child) carries a pass-through coefficient c in [0,1] for its
dependency type. The fraction of the parent's value hit by a child losing `s` of its value
is roughly c * (exposure_pct/100) * s. Production propagation uses flat per-type coefficients:
oracle=0.70, liquidity=0.35. LLTV is displayed in labels only. The liquidation_loss helper
below is unused; wiring a calibrated LLTV rule into propagation remains future work.

Defaults are modelling assumptions informed by a small set of incidents, not a statistically
validated calibration. Separate exit-cost calculations estimate slippage and liquidity.
"""
from __future__ import annotations

# Pass-through coefficient by dependency (edge) type.
PASS_THROUGH = {
    "chain": 1.00,       # settlement-layer failure hits everything above it in full
    "issuer": 0.90,      # issuer insolvency / key compromise largely reaches the token
    "backing": 0.95,     # a depeg of the backing asset flows into the wrapper almost fully
    "collateral": 0.85,  # collateral loss in a lending market -> vault NAV, net of over-collateralisation
    "oracle": 0.70,      # oracle failure -> mispricing/liquidation, partially recoverable
    "liquidity": 0.35,   # AMM/liquidity drain is mostly an exit-cost, not full MTM loss
}
DEFAULT_PASS_THROUGH = 0.80

# Liquidation rule: a loss on collateral worth `s` triggers a liquidation on the lending
# market when the resulting collateral value falls below the LLTV. Severity above LLTV is
# amplified by the liquidation penalty.
LIQUIDATION_PENALTY = 0.05  # typical incentive/penalty on seized collateral


def pass_through(dep_type: str) -> float:
    return PASS_THROUGH.get(dep_type, DEFAULT_PASS_THROUGH)


def liquidation_loss(collateral_shock: float, lltv: float) -> float:
    """Fraction of a lending position lost when collateral drops by `collateral_shock`.

    If the collateral's remaining value (1 - shock) stays above LLTV, no liquidation (0 loss
    to the supplier). Once it breaches LLTV, the supplier is exposed to the shortfall plus the
    liquidation penalty (bad debt begins accruing beyond full collateral consumption).
    """
    remaining = 1.0 - collateral_shock
    if remaining >= lltv:
        return 0.0
    # Shortfall below the liquidation threshold, amplified by the penalty, capped at 1.
    shortfall = (lltv - remaining) / max(lltv, 1e-6)
    return min(1.0, shortfall * (1.0 + LIQUIDATION_PENALTY))
