"""Monte-Carlo failure propagation up the dependency graph.

Each simulated path samples, at every node, whether an incident occurs (Bernoulli with the
node's horizon probability) and its severity (Beta per risk category) -> an intrinsic shock
s_n in [0,1]. Losses then propagate UP the graph with a *multiplicative* survival rule:

    loss[n] = 1 - (1 - s_n) * prod over dependencies d of (1 - c(n->d) * share * loss[d])

computed leaves-first. This bounds every node's loss in [0,1] and, crucially, does not
double-count a shared ancestor reached through several paths (e.g. an issuer behind both a
wrapper and its underlying) the way a naive path-sum would. The position's loss is loss[root].

Attribution: per path we split the realised position loss across nodes by weight
s_n * T_dom[n] (dominant-path transmission, capped at 1), so contributions sum to the expected
loss and the UI can say "X% of expected loss comes from this dependency path".

`force` overrides pin a node to a chosen probability/severity for the what-if panel.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx
import numpy as np

from ..discovery.graph import DependencyGraph
from ..models import incidents, severity
from ..models.passthrough import pass_through


@dataclass
class RiskResult:
    horizon_months: float
    el: float
    cvar95: float
    var95: float
    p_any_loss: float
    loss_samples: np.ndarray
    transmission: dict        # node_id -> dominant-path transmission (<=1)
    node_prob: dict           # node_id -> horizon incident probability
    node_contrib: dict        # node_id -> expected fractional contribution to position loss
    contrib_by_type: dict = field(default_factory=dict)


def _edge_factor(g: DependencyGraph, u: str, v: str) -> float:
    e = g.edge(u, v)
    return pass_through(e.dep_type) * (e.exposure_pct / 100.0)


def _dominant_transmission(g: DependencyGraph) -> dict:
    """Max over paths root->n of the product of edge factors, capped at 1 (no double count)."""
    T: dict[str, float] = {g.root_id: 1.0}
    for n in nx.topological_sort(g.g):
        if n == g.root_id:
            continue
        best = 0.0
        for p in g.g.predecessors(n):
            best = max(best, T.get(p, 0.0) * _edge_factor(g, p, n))
        T[n] = min(best, 1.0)
    return T


def propagate(g: DependencyGraph, horizon_months: float, n_paths: int = 20000,
              seed: int = 42, force: dict | None = None) -> RiskResult:
    force = force or {}
    rng = np.random.default_rng(seed)

    # 1) sample intrinsic shocks per node
    shocks: dict[str, np.ndarray] = {}
    node_prob: dict[str, float] = {}
    for node in g.nodes():
        nid = node.id
        rc = node.meta.get("risk_category")
        p = incidents.node_incident_prob(rc, horizon_months, node.kind)["prob"]
        sev_mean = None
        if nid in force:
            p = float(force[nid].get("prob", 1.0))
            sev_mean = force[nid].get("severity")
        node_prob[nid] = p
        occur = rng.random(n_paths) < p
        sev = (np.full(n_paths, float(sev_mean)) if sev_mean is not None
               else severity.sample_severity(rc, node.kind, rng, n_paths))
        shocks[nid] = occur * sev

    # 2) multiplicative propagation, leaves-first
    loss: dict[str, np.ndarray] = {}
    for nid in reversed(list(nx.topological_sort(g.g))):
        surv = 1.0 - shocks[nid]
        for c in g.g.successors(nid):
            surv = surv * (1.0 - _edge_factor(g, nid, c) * loss[c])
        loss[nid] = 1.0 - surv

    total = np.clip(loss[g.root_id], 0.0, 1.0)

    # 3) attribution (weights sum per path -> contributions sum to EL)
    T = _dominant_transmission(g)
    weights = {nid: shocks[nid] * T.get(nid, 0.0) for nid in shocks}
    wsum = np.zeros(n_paths)
    for w in weights.values():
        wsum += w
    safe = np.where(wsum > 0, wsum, 1.0)
    node_contrib, contrib_by_type = {}, {}
    for node in g.nodes():
        nid = node.id
        contrib = float((total * weights[nid] / safe).mean())
        node_contrib[nid] = contrib
        preds = list(g.g.predecessors(nid))
        dep_type = g.edge(preds[0], nid).dep_type if preds else "position"
        contrib_by_type[dep_type] = contrib_by_type.get(dep_type, 0.0) + contrib

    el = float(total.mean())
    var95 = float(np.quantile(total, 0.95))
    tail = total[total >= var95]
    cvar95 = float(tail.mean()) if tail.size else var95
    return RiskResult(
        horizon_months=horizon_months, el=el, cvar95=cvar95, var95=var95,
        p_any_loss=float((total > 0.005).mean()), loss_samples=total,
        transmission=T, node_prob=node_prob, node_contrib=node_contrib,
        contrib_by_type=contrib_by_type,
    )


def top_contributors(g: DependencyGraph, res: RiskResult, k: int = 6) -> list[dict]:
    rows = []
    for nid, c in sorted(res.node_contrib.items(), key=lambda kv: kv[1], reverse=True):
        if c <= 0:
            continue
        node = g.node(nid)
        rows.append({
            "node": node.label, "kind": node.kind,
            "risk_category": node.meta.get("risk_category"),
            "incident_prob": res.node_prob.get(nid, 0.0),
            "transmission": res.transmission.get(nid, 0.0),
            "expected_contrib": c, "share_of_el": c / res.el if res.el > 0 else 0.0,
        })
        if len(rows) >= k:
            break
    return rows
