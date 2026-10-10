"""Discrete least-cost protection with shared continuous withdrawal resources."""
from __future__ import annotations

import math

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

UNIT = 1_000_000.0
TOL = .02  # USD; solely numerical feasibility tolerance


def verify_plan(stress: dict, execution: dict, actions: list[dict], withdrawals: list[dict],
                locks: list[str], loss_limit: float | None) -> dict:
    """Independent, dollar-unit audit of the solver output and candidate identity."""
    rows = {r["id"]: r for r in stress["positions"]}
    if {a["id"] for a in actions} != set(rows) or len(actions) != len(rows):
        raise ValueError("Plan must contain exactly one action for each position")
    selected, by_market, by_vault = {}, {}, {}
    for a in actions:
        candidates = execution["options"][a["id"]]
        option = next((o for o in candidates if abs(o["fraction"] - a["fraction"]) < 1e-9), None)
        if option is None:
            raise ValueError("Unavailable exit selected")
        for field in ("notional_usd", "execution_usd", "conversion_usd", "carry_usd"):
            if not math.isfinite(a[field]) or abs(a[field] - option[field]) > TOL:
                raise ValueError("Action differs from quoted candidate")
        if a["id"] in locks and a["fraction"] != 0:
            raise ValueError("Locked position sold")
        selected[a["id"]] = option
    for w in withdrawals:
        amount, pid, mid = w["amount_usd"], w["position"], w["market"]
        cap = execution["vault_caps"].get(pid, {}).get(mid)
        if cap is None or not math.isfinite(amount) or amount < -TOL or amount > cap + TOL:
            raise ValueError("Invalid vault withdrawal resource")
        if (pid, mid) in by_vault:
            raise ValueError("Duplicate withdrawal resource")
        by_vault[(pid, mid)] = amount
        by_market[mid] = by_market.get(mid, 0) + amount
    for mid, amount in by_market.items():
        if amount > execution["resources"][mid] + TOL:
            raise ValueError("Shared market liquidity exceeded")
    for pid in execution["vault_caps"]:
        used = sum(v for (p, _), v in by_vault.items() if p == pid)
        if abs(used - selected[pid]["notional_usd"]) > TOL:
            raise ValueError("Withdrawal funding does not match sale")
    avoided = sum(rows[pid]["loss_usd"] * o["fraction"] for pid, o in selected.items())
    execution_usd = sum(o["execution_usd"] for o in selected.values())
    conversion = sum(o["conversion_usd"] for o in selected.values())
    carry = sum(o["carry_usd"] for o in selected.values())
    sold = sum(o["notional_usd"] for o in selected.values())
    residual = max(0, stress["loss_usd"] - avoided)
    accounted = residual + execution_usd + conversion
    return {"verified": True, "avoided_loss_usd": avoided, "residual_loss_usd": residual,
            "execution_usd": execution_usd, "conversion_usd": conversion, "carry_usd": carry,
            "protection_cost_usd": execution_usd + conversion + carry,
            "capital_sold_usd": sold, "capital_released_usd": sold - execution_usd - conversion,
            "accounted_loss_usd": accounted,
            "meets_limit": loss_limit is None or accounted <= loss_limit + TOL,
            "break_even_probability": (execution_usd + conversion + carry) / avoided if avoided > 0 else None,
            "market_use": [{"market": m, "used_usd": amount, "capacity_usd": execution["resources"][m]}
                           for m, amount in sorted(by_market.items())]}


def plan_rescue(stress: dict, execution: dict, loss_limit_usd: float,
                locked_positions: list[str] | None = None, *, mode: str = "protect",
                time_limit: float = 3.0) -> dict:
    if not math.isfinite(loss_limit_usd) or loss_limit_usd < 0:
        raise ValueError("Loss limit must be finite and nonnegative")
    if mode not in ("protect", "minimum_loss", "exit_affected"):
        raise ValueError("Unknown optimization mode")
    locks = sorted(set(locked_positions or []))
    rows = {r["id"]: r for r in stress["positions"]}
    if set(locks) - rows.keys():
        raise ValueError("Unknown locked position")
    choices = [(pid, o) for pid in sorted(rows) for o in execution["options"][pid]]
    resources = [(pid, mid, cap) for pid, caps in sorted(execution["vault_caps"].items())
                 for mid, cap in sorted(caps.items())]
    nx, n = len(choices), len(choices) + len(resources)
    lower, upper = np.zeros(n), np.ones(n)
    for i, (pid, o) in enumerate(choices):
        if pid in locks and o["fraction"] > 0:
            upper[i] = 0
        if mode == "exit_affected":
            required = 1.0 if rows[pid]["loss_usd"] > 0 else 0.0
            if o["fraction"] != required:
                upper[i] = 0
    for j, (_, _, cap) in enumerate(resources, nx):
        upper[j] = cap / UNIT
    matrix, lb, ub = [], [], []

    def constraint(coefficients, low, high):
        row = np.zeros(n)
        for i, value in coefficients:
            row[i] = value
        matrix.append(row)
        lb.append(low)
        ub.append(high)

    for pid in sorted(rows):
        constraint([(i, 1) for i, (p, _) in enumerate(choices) if p == pid], 1, 1)
    for pid in sorted(execution["vault_caps"]):
        constraint([(i, -o["notional_usd"] / UNIT) for i, (p, o) in enumerate(choices) if p == pid] +
                   [(j, 1) for j, (p, _, _) in enumerate(resources, nx) if p == pid], 0, 0)
    for mid, cap in sorted(execution["resources"].items()):
        constraint([(j, 1) for j, (_, m, _) in enumerate(resources, nx) if m == mid], 0, cap / UNIT)
    loss_change = np.zeros(n)
    costs = np.zeros(n)
    sales = np.zeros(n)
    for i, (pid, o) in enumerate(choices):
        loss_change[i] = (-rows[pid]["loss_usd"] * o["fraction"] + o["execution_usd"] + o["conversion_usd"]) / UNIT
        costs[i] = (o["execution_usd"] + o["conversion_usd"] + o["carry_usd"]) / UNIT
        sales[i] = o["notional_usd"] / UNIT
    if mode == "protect":
        constraint(list(enumerate(loss_change)), -np.inf, (loss_limit_usd - stress["loss_usd"]) / UNIT)
    objective = loss_change if mode == "minimum_loss" else costs
    integrality = np.r_[np.ones(nx), np.zeros(n - nx)]

    def solve(obj):
        return milp(obj, integrality=integrality, bounds=Bounds(lower, upper),
                    constraints=LinearConstraint(np.array(matrix), lb, ub),
                    options={"time_limit": time_limit, "mip_rel_gap": 0.0})

    result = solve(objective)
    if result.x is None:
        if result.status == 2 and mode == "protect":
            best = plan_rescue(stress, execution, loss_limit_usd, locks, mode="minimum_loss", time_limit=time_limit)
            if best.get("audit"):
                best.update(status="infeasible" if best["optimal"] else "unresolved",
                            target_met=False, message="Target is below attainable snapshot protection" if best["optimal"]
                            else "No target-feasible plan found; best attainable bound not proved",
                            minimum_attainable_proved=best["optimal"])
            return best
        return {"status": "infeasible" if result.status == 2 else "unresolved", "optimal": False,
                "target_met": False, "message": str(result.message), "actions": [], "withdrawals": [],
                "loss_limit_usd": loss_limit_usd, "locks": locks, "mode": mode}
    optimal = result.status == 0
    if optimal and mode == "protect":
        # Lexicographic tie-break: preserve proved economic cost to a fraction
        # of one cent, then release the least capital.
        constraint(list(enumerate(costs)), -np.inf, float(costs @ result.x) + 1e-10)
        secondary = solve(sales)
        if secondary.status == 0 and secondary.x is not None:
            result = secondary
    actions = []
    for i, (pid, o) in enumerate(choices):
        if result.x[i] > .5:
            actions.append({"id": pid, "label": rows[pid]["label"], **o,
                            "avoided_loss_usd": rows[pid]["loss_usd"] * o["fraction"]})
    withdrawals = [{"position": pid, "market": mid, "amount_usd": max(0.0, float(result.x[j] * UNIT))}
                   for j, (pid, mid, _) in enumerate(resources, nx) if result.x[j] > 1e-10]
    try:
        audit = verify_plan(stress, execution, actions, withdrawals, locks, loss_limit_usd)
        if mode == "protect" and not audit["meets_limit"]:
            raise ValueError("Solver candidate violates the requested loss limit")
    except ValueError as e:
        return {"status": "verification_failed", "optimal": False, "target_met": False,
                "message": str(e), "actions": [], "withdrawals": [], "mode": mode}
    return {"status": "optimal" if optimal else "feasible_incumbent", "optimal": optimal,
            "target_met": audit["meets_limit"], "audit": audit, "actions": actions,
            "withdrawals": withdrawals, "loss_limit_usd": loss_limit_usd, "locks": locks,
            "mode": mode, "message": str(result.message),
            "mip_gap": float(result.mip_gap) if getattr(result, "mip_gap", None) is not None else None}
