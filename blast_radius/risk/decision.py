"""The portfolio manager's question: is the expected loss from staying high enough to justify
exiting despite slippage and execution costs?

We compare the expected net P&L of holding over the horizon (carry earned minus expected loss
from dependency failures) against the cost of exiting now. A large tail (CVaR-95) can turn an
otherwise-fine position into a REDUCE even when the mean is acceptable.

    carry      = position APY x horizon
    EL         = expected loss over horizon (Monte-Carlo mean)
    exit_cost  = slippage + fees to unwind now
    net_stay   = carry - EL                     (expected P&L if you hold)
    EXIT   when EL - carry >  exit_cost          (holding's expected loss beats the exit cost)
    STAY   when EL - carry <= 0  and CVaR tolerable
    REDUCE otherwise (marginal, or tail too fat)
"""
from __future__ import annotations

from .propagate import RiskResult, top_contributors


def decide(g, res: RiskResult, exit_info: dict, apy: float, horizon_months: float,
           tail_tolerance: float = 0.15) -> dict:
    carry = (apy or 0.0) * horizon_months / 12.0
    el = res.el
    exit_cost = exit_info.get("cost_pct", 0.0)
    net_stay = carry - el
    tail_bad = res.cvar95 > tail_tolerance

    if el - carry > exit_cost:
        verdict = "EXIT"
    elif net_stay >= 0 and not tail_bad:
        verdict = "STAY"
    else:
        verdict = "REDUCE"

    contribs = top_contributors(g, res, k=5)
    dominant = contribs[0] if contribs else None
    path = _dominant_path(g, dominant["node"]) if dominant else ""

    reason = _explain(verdict, carry, el, exit_cost, res, dominant, path, horizon_months, tail_bad)
    return {
        "verdict": verdict, "carry": carry, "el": el, "cvar95": res.cvar95,
        "exit_cost": exit_cost, "net_stay": net_stay, "horizon_months": horizon_months,
        "dominant": dominant, "dominant_path": path, "top_contributors": contribs,
        "reason": reason, "tail_bad": tail_bad,
    }


def _dominant_path(g, label: str) -> str:
    """Shortest dependency path root -> the dominant node, as 'A → B → C'."""
    import networkx as nx
    target = next((n.id for n in g.nodes() if n.label == label), None)
    if not target:
        return label
    try:
        ids = nx.shortest_path(g.g, g.root_id, target)
        return " → ".join(g.node(i).label for i in ids)
    except Exception:
        return label


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def _explain(verdict, carry, el, exit_cost, res, dominant, path, horizon, tail_bad) -> str:
    h = f"{horizon:.0f}-month"
    base = (f"Over a {h} horizon the position earns ~{_pct(carry)} carry against "
            f"~{_pct(el)} expected loss from dependency failures (CVaR-95 {_pct(res.cvar95)}). "
            f"Unwinding now costs ~{_pct(exit_cost)}.")
    if dominant:
        base += (f" The dominant risk is **{path or dominant['node']}** "
                 f"({_pct(dominant['share_of_el'])} of expected loss: "
                 f"{_pct(dominant['incident_prob'])} incident probability, "
                 f"{dominant['transmission'] * 100:.0f}% transmission to the position).")
    if verdict == "EXIT":
        base += (f" **EXIT:** expected loss exceeds carry by more than the {_pct(exit_cost)} "
                 f"exit cost — you are not being paid for this risk and can leave cheaply.")
    elif verdict == "STAY":
        base += (" **STAY:** carry more than covers the expected loss and the tail is within "
                 "tolerance — exiting would forfeit positive risk-adjusted yield.")
    else:
        why = "the tail loss is large" if tail_bad else "carry barely covers the expected loss"
        base += f" **REDUCE:** {why}; trim exposure rather than pay full exit cost or hold the full tail."
    return base
