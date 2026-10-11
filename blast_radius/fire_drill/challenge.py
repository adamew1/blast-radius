"""Bounded allocations to supported instruments; never edit instrument identity."""
from __future__ import annotations

import math

STEP_USD = 50_000
MAX_POSITION_USD = 2_000_000
MAX_POSITIONS = 10


def resize_positions(supported: list[dict], sizes: dict | None = None) -> list[dict]:
    """Zero removes a position. Amounts are allocations, not recorded trades."""
    if sizes is None:
        return [dict(p) for p in supported]
    if not isinstance(sizes, dict) or set(sizes) != {p["id"] for p in supported}:
        raise ValueError("Supply one allocation for each supported instrument")
    positions = []
    for p in supported:
        size = sizes[p["id"]]
        if (isinstance(size, bool) or not isinstance(size, (int, float))
                or not math.isfinite(size) or not 0 <= size <= MAX_POSITION_USD
                or size % STEP_USD != 0):
            raise ValueError("Allocations must be $0–$2M in $50,000 steps")
        if size:
            positions.append({**p, "size_usd": int(size)})
    if not positions:
        raise ValueError("Keep at least one position")
    if len(positions) > MAX_POSITIONS:
        raise ValueError("Select at most ten instruments for this demonstration")
    return positions
