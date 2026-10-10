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


def empirical_severity_table() -> list[dict]:
    """Loss distribution per hack classification from the real /hacks dataset.

    loss/TVL uses the protocol's CURRENT TVL as a (rough, post-incident) denominator — a
    documented approximation. Reported for transparency; the Beta means above are informed by it.
    """
    import statistics as stats
    from collections import defaultdict

    from ..sources import defillama

    tvl = {str(p.get("id")): (p.get("tvl") or 0.0) for p in defillama.protocols()}
    by_clf: dict[str, list] = defaultdict(list)
    for h in defillama.hacks():
        clf, amt = h.get("classification"), h.get("amount") or 0
        if not clf or amt <= 0:
            continue
        pid = str(h["defillamaId"]) if h.get("defillamaId") is not None else None
        ratio = (amt / tvl[pid]) if pid and tvl.get(pid, 0) > 0 else None
        by_clf[clf].append((amt, ratio))
    rows = []
    for clf, vals in by_clf.items():
        amts = [a for a, _ in vals]
        ratios = [min(r, 1.0) for _, r in vals if r is not None]
        rows.append({"classification": clf, "n": len(amts),
                     "median_loss_usd": stats.median(amts),
                     "median_loss_over_tvl": round(stats.median(ratios), 3) if ratios else None})
    return sorted(rows, key=lambda r: -r["n"])
