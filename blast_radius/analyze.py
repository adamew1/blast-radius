"""Top-level orchestrator: position dict -> dependency graph + risk + exit cost + verdict."""
from __future__ import annotations

from .config import load_config
from .discovery.engine import build_graph, summarize
from .risk.decision import decide
from .risk.exit_cost import exit_cost
from .risk.propagate import propagate


def analyze_position(position: dict, horizon_months: float | None = None,
                     n_paths: int | None = None, seed: int | None = None,
                     force: dict | None = None, exit_info: dict | None = None) -> dict:
    cfg = load_config()
    H = horizon_months or cfg.get("horizon_months", 12)
    mc = cfg.get("monte_carlo", {})
    dec_cfg = cfg.get("decision", {})

    g = build_graph(position)
    res = propagate(g, H, n_paths=n_paths or mc.get("n_paths", 20000),
                    seed=seed if seed is not None else mc.get("seed", 42), force=force)
    ex = exit_info if exit_info is not None else exit_cost(position)
    apy = g.node(g.root_id).meta.get("apy", 0.0)
    dec = decide(g, res, ex, apy, H, tail_tolerance=dec_cfg.get("tail_tolerance", 0.15))

    return {"position": position, "graph": g, "risk": res, "exit": ex, "decision": dec,
            "summary": summarize(g), "apy": apy, "horizon": H}
