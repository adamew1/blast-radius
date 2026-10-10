"""Incident-probability model.

Base-rate backbone (always available): per-protocol annual hazard by DefiLlama category
and by hack *classification*, computed from the real /hacks dataset joined to /protocols
metadata. A LightGBM panel model (Phase 6) can override category rates where it beats the
baseline; until then the base rate is used directly.

Depegs are not "hacks", so /hacks under-counts stablecoin peg failures. For stablecoin-like
categories we blend the hack-derived rate with a small, DOCUMENTED depeg prior (flagged as a
prior in the UI). Everything is transparent via `category_table()`.
"""
from __future__ import annotations

import datetime as dt
import math
from functools import lru_cache

from ..sources import defillama

# Hazard estimation window (years). DeFi hack activity before ~2020 is not representative.
_WINDOW_START_YEAR = 2020
_NOW_YEAR = 2026

# Documented annual depeg/failure priors for categories /hacks does not capture well.
# These are PRIORS (labelled in the UI), grounded in the 2022-2025 track record of each class.
_DEPEG_PRIORS = {
    "Stablecoin (fiat)": 0.01,     # USDC briefly depegged Mar-2023 (SVB); rare, recovers.
    "CDP stablecoin": 0.015,       # DAI/USDS style; robust but collateral-dependent.
    "Synthetic Dollar": 0.08,      # USDe/deUSD/xUSD class: higher peg-failure track record.
    "Yield (savings)": 0.04,       # savings wrappers inherit their stablecoin's peg risk.
}
_DEPEG_PRIOR_SOURCE = "2022-2025 stablecoin peg-failure track record (UST, USDC-SVB, USDe, deUSD, xUSD)"

# Native-asset / major-chain hazards (settlement layer). Documented priors; Ethereum L1 has
# never suffered a value-loss consensus failure.
_CHAIN_PRIORS = {"Chain": 0.005, "Native asset": 0.005}


@lru_cache(maxsize=1)
def _protocol_index() -> dict:
    """id -> {category, name, chains, tvl}."""
    idx = {}
    for p in defillama.protocols():
        pid = str(p.get("id"))
        idx[pid] = {
            "category": p.get("category"),
            "name": p.get("name"),
            "tvl": p.get("tvl") or 0.0,
        }
    return idx


@lru_cache(maxsize=1)
def _category_protocol_counts() -> dict:
    counts: dict[str, int] = {}
    for p in defillama.protocols():
        c = p.get("category")
        if c:
            counts[c] = counts.get(c, 0) + 1
    return counts


@lru_cache(maxsize=1)
def _hack_stats() -> dict:
    """Compute category & classification hack counts within the window."""
    idx = _protocol_index()
    cat_hacks: dict[str, int] = {}
    clf_hacks: dict[str, int] = {}
    total = 0
    for h in defillama.hacks():
        ts = h.get("date")
        if not ts:
            continue
        year = dt.datetime.fromtimestamp(ts, dt.timezone.utc).year
        if year < _WINDOW_START_YEAR:
            continue
        total += 1
        clf = h.get("classification")
        if clf:
            clf_hacks[clf] = clf_hacks.get(clf, 0) + 1
        pid = str(h.get("defillamaId")) if h.get("defillamaId") is not None else None
        cat = idx.get(pid, {}).get("category") if pid else None
        if cat:
            cat_hacks[cat] = cat_hacks.get(cat, 0) + 1
    return {"cat_hacks": cat_hacks, "clf_hacks": clf_hacks, "total": total}


def _years() -> float:
    return float(_NOW_YEAR - _WINDOW_START_YEAR)


@lru_cache(maxsize=1)
def _total_protocols() -> int:
    return len(defillama.protocols())


def category_hazard(category: str | None) -> float:
    """Annual per-protocol probability of a value-impacting hack for a DefiLlama category."""
    stats = _hack_stats()
    counts = _category_protocol_counts()
    years = _years()
    if category and category in stats["cat_hacks"] and counts.get(category):
        return stats["cat_hacks"][category] / (counts[category] * years)
    # Fallback: overall per-protocol hazard.
    return stats["total"] / (_total_protocols() * years)


def classification_hazard(classification: str) -> float:
    """Annual per-protocol probability that *any* protocol suffers this attack class."""
    stats = _hack_stats()
    n = stats["clf_hacks"].get(classification, 0)
    return n / (_total_protocols() * _years())


def _prob(hazard: float, horizon_months: float) -> float:
    return 1.0 - math.exp(-max(hazard, 0.0) * horizon_months / 12.0)


def node_hazard(risk_category: str | None, node_kind: str | None = None) -> tuple[float, str]:
    """Return (annual_hazard, basis_label) for a node's risk category / kind."""
    if node_kind == "oracle":
        return classification_hazard("Oracle Manipulation"), "hacks:Oracle Manipulation"
    if risk_category in _CHAIN_PRIORS:
        return _CHAIN_PRIORS[risk_category], f"prior:settlement-layer ({_DEPEG_PRIOR_SOURCE[:0] or 'L1 track record'})"
    if risk_category in _DEPEG_PRIORS:
        # Blend the category hack-rate with the documented depeg prior (max = dominant risk).
        h_hack = category_hazard(risk_category)
        return max(h_hack, _DEPEG_PRIORS[risk_category]), "prior:depeg + hacks"
    return category_hazard(risk_category), f"hacks:category={risk_category or 'overall'}"


def node_incident_prob(risk_category: str | None, horizon_months: float,
                       node_kind: str | None = None) -> dict:
    hazard, basis = node_hazard(risk_category, node_kind)
    return {"hazard": hazard, "prob": _prob(hazard, horizon_months), "basis": basis}


def category_table(horizon_months: float = 12) -> list[dict]:
    """Transparency table: hazard + horizon probability per category (for README/UI)."""
    stats = _hack_stats()
    counts = _category_protocol_counts()
    rows = []
    cats = set(stats["cat_hacks"]) | set(_DEPEG_PRIORS)
    for c in sorted(cats):
        h, basis = node_hazard(c)
        rows.append({
            "category": c,
            "protocols": counts.get(c, 0),
            "hacks_in_window": stats["cat_hacks"].get(c, 0),
            "annual_hazard": round(h, 4),
            "prob_horizon": round(_prob(h, horizon_months), 4),
            "basis": basis,
        })
    return sorted(rows, key=lambda r: r["annual_hazard"], reverse=True)
