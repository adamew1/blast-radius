"""Loss-severity model: the fraction of a node's value destroyed *given* an incident.

Thin-slice defaults live here, keyed by risk category. Phase 3 fits loss/TVL distributions
per hack classification from the real /hacks dataset and overrides these means; the Beta
sampler is already shaped so the Monte-Carlo layer can draw from it unchanged.
"""
from __future__ import annotations

import numpy as np

# Mean fraction of exposed value lost, conditional on an incident occurring.
# Grounded in the 2023-2025 loss record for each class; refined in Phase 3 from /hacks.
SEVERITY_MEAN = {
    "Oracle Manipulation": 0.35,
    "Chain": 0.25,
    "Native asset": 0.20,
    "Liquid Staking": 0.15,
    "Liquid Restaking": 0.22,
    "Synthetic Dollar": 0.60,
    "CDP stablecoin": 0.25,
    "Stablecoin (fiat)": 0.12,
    "Yield (savings)": 0.35,
    "Wrapped BTC (custodial)": 0.30,
    "Lending": 0.45,
    "Dexs": 0.40,
    "Yield": 0.40,
}
DEFAULT_SEVERITY = 0.40

# Beta concentration: higher => tighter around the mean. Loss outcomes are heavy-tailed,
# so keep it loose enough that the tail (CVaR) is meaningful.
_CONCENTRATION = 4.0


def severity_mean(risk_category: str | None, node_kind: str | None = None) -> float:
    if node_kind == "oracle":
        return SEVERITY_MEAN["Oracle Manipulation"]
    return SEVERITY_MEAN.get(risk_category, DEFAULT_SEVERITY)


def _beta_params(mean: float, concentration: float = _CONCENTRATION) -> tuple[float, float]:
    mean = min(max(mean, 1e-3), 1 - 1e-3)
    a = mean * concentration
    b = (1 - mean) * concentration
    return a, b


def sample_severity(risk_category: str | None, node_kind: str | None,
                    rng: np.random.Generator, size: int) -> np.ndarray:
    """Draw loss fractions in [0,1] from a Beta with the category mean."""
    a, b = _beta_params(severity_mean(risk_category, node_kind))
    return rng.beta(a, b, size=size)
