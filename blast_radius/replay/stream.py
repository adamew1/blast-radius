"""Stream Finance → Elixir deUSD contagion replay (November 2025).

Dependency STRUCTURE is reconstructed from sourced post-mortems (data/replay/stream_snapshot.yaml);
the PRICE SERIES driving the replay are REAL daily DefiLlama series for xUSD/deUSD/sdeUSD.

Each day we force Stream xUSD's shock to its observed peg deviation and propagate it through the
dependency graph to the sdeUSD holding — i.e. we only use information visible on that day. The
verdict flips to EXIT when xUSD breaks (Nov 4), three days before deUSD/sdeUSD actually collapse
(Nov 7). The "avoided loss" is then computed from the REAL sdeUSD price at the signal date vs the
end — never a number the replay doesn't actually compute.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache

import yaml

from ..config import REPLAY, load_config
from ..discovery.graph import DependencyGraph, Edge, Node
from ..risk.decision import decide
from ..risk.propagate import propagate
from ..sources import defillama

_EXIT_COST = 0.01   # brief's worked-example 1% slippage assumption
_HORIZON_M = 0.5    # the decision is "ride out the next ~2 weeks or not"


@lru_cache(maxsize=1)
def load_snapshot() -> dict:
    return yaml.safe_load((REPLAY / "stream_snapshot.yaml").read_text(encoding="utf-8"))


def build_graph(snapshot: dict | None = None) -> DependencyGraph:
    snap = snapshot or load_snapshot()
    root_id = next(n["id"] for n in snap["nodes"] if n["kind"] == "position")
    g = DependencyGraph(root_id=root_id)
    for n in snap["nodes"]:
        g.add_node(Node(id=n["id"], kind=n["kind"], label=n["label"], chain="ethereum",
                        meta={"risk_category": n.get("risk_category"), "source": n.get("source"),
                              "price_name": n.get("price_name"), "reconstructed": True}))
    for e in snap["edges"]:
        g.add_edge(Edge(parent=e["parent"], child=e["child"], dep_type=e["dep_type"],
                        exposure_pct=float(e.get("exposure_pct", 100)), source="reconstructed",
                        note=e.get("note", "")))
    g.node(g.root_id).meta.update({"apy": 0.0, "size_usd": snap["position"]["size_usd"]})
    return g


def _unix(date_str: str) -> int:
    return int(dt.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp())


@lru_cache(maxsize=1)
def load_series() -> dict:
    """{coin_name: {date_str: price}} from the cached real DefiLlama chart series."""
    cfg = load_config()
    rep = cfg["replay"]["stream"]
    start, span = _unix(rep["window"]["start"]), rep["window"]["span"]
    out: dict[str, dict] = {}
    for name, key in rep["coins"].items():
        series = defillama.chart(key, start=start, span=span, period="1d")
        pts = ((series.get("coins") or {}).get(key) or {}).get("prices", [])
        by_date: dict[str, float] = {}
        for p in pts:
            # snap each point to the nearest UTC midnight so labels match the calendar.
            ts = round(p["timestamp"] / 86400) * 86400
            d = dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d")
            by_date[d] = p["price"]        # keep last sample for the day
        out[name] = by_date
    return out


def _dates() -> list[str]:
    series = load_series()
    all_dates = sorted({d for by in series.values() for d in by})
    return all_dates


def _price_on(name: str, date: str, dates: list[str]) -> float | None:
    """Forward-filled real price for `name` on `date`."""
    by = load_series().get(name, {})
    val = None
    for d in dates:
        if d > date:
            break
        if d in by:
            val = by[d]
    return val


def _nearest_event(events: dict, date: str) -> str:
    chosen = ""
    for d in sorted(events):
        if d <= date:
            chosen = events[d]
    return chosen


@lru_cache(maxsize=1)
def compute_frames() -> dict:
    snap = load_snapshot()
    g = build_graph(snap)
    dates = _dates()
    base = snap["baseline"]
    events = snap.get("events", {})
    xusd_node = "token:xusd"

    frames = []
    first_exit = None
    for date in dates:
        prices = {name: _price_on(name, date, dates) for name in base}
        px = prices.get("xUSD")
        xusd_shock = max(0.0, 1.0 - px / base["xUSD"]) if px else 0.0
        force = {xusd_node: {"prob": 1.0, "severity": xusd_shock}} if xusd_shock > 0.01 else None

        res = propagate(g, _HORIZON_M, n_paths=5000, seed=7, force=force)
        exit_info = {"cost_pct": _EXIT_COST, "method": "assumed 1% slippage (brief)",
                     "detail": "fixed 1% unwind cost per the PM worked example"}
        dec = decide(g, res, exit_info, apy=0.0, horizon_months=_HORIZON_M)
        if dec["verdict"] == "EXIT" and first_exit is None:
            first_exit = date

        shares = {nid: (c / res.el if res.el else 0.0) for nid, c in res.node_contrib.items()}
        frames.append({
            "date": date, "prices": prices, "xusd_shock": xusd_shock,
            "verdict": dec["verdict"], "el": dec["el"], "cvar95": dec["cvar95"],
            "reason": dec["reason"], "shares": shares,
            "narrative": _nearest_event(events, date),
        })

    hero = _hero(frames, first_exit, dates)
    return {"dates": dates, "frames": frames, "first_exit": first_exit, "hero": hero,
            "sources": snap.get("sources", [])}


def _hero(frames: list, first_exit: str | None, dates: list[str]) -> dict:
    """Honest avoided-loss: real sdeUSD at the tool's EXIT signal vs at the end, and the
    contrast with a naive price-watcher who only exits once sdeUSD itself visibly breaks."""
    def sde(date):
        return _price_on("sdeUSD", date, dates)

    end = dates[-1]
    p_end = sde(end) or 0.0
    # naive price-watcher: first day sdeUSD itself has fallen > 5% from baseline
    base_sde = load_snapshot()["baseline"]["sdeUSD"]
    naive_exit = next((f["date"] for f in frames
                       if (sde(f["date"]) or base_sde) < 0.95 * base_sde), end)

    out = {"end_date": end, "sdeusd_end": p_end,
           "naive_exit_date": naive_exit, "sdeusd_naive": sde(naive_exit)}
    if first_exit:
        p_sig = sde(first_exit) or 0.0
        out.update({
            "signal_date": first_exit, "sdeusd_signal": p_sig,
            "avoided_loss_pct": (p_sig - p_end) / p_sig if p_sig else 0.0,
            "naive_loss_pct": ((sde(naive_exit) or 0.0) - p_end) / (sde(naive_exit) or 1.0),
            "lead_days": (dt.datetime.strptime(naive_exit, "%Y-%m-%d")
                          - dt.datetime.strptime(first_exit, "%Y-%m-%d")).days,
        })
    return out
