"""Portfolio book: analyse up to ~10 positions, find shared dependencies, rank actions.

Shared-dependency detection relies on canonical node ids (token:chain:addr, issuer:key,
oracle:addr, lmkt:morpho:marketId, chain:name) so the *same* underlying dependency collapses
to one node across positions — that's how we can say "N of your 10 positions depend on X".
"""
from __future__ import annotations

import json
from pathlib import Path

from ..analyze import analyze_position
from ..config import BOOK

# dependency kinds worth surfacing as "shared" (chain is trivially shared; keep it last)
_SHARE_KINDS = ("issuer", "token", "oracle", "lending_market", "amm", "chain")


def load_book(path: str | Path | None = None) -> dict:
    p = Path(path) if path else (BOOK / "sample_book.json")
    return json.loads(Path(p).read_text(encoding="utf-8"))


def analyze_book(positions: list[dict], n_paths: int = 8000) -> dict:
    per = []
    for pos in positions:
        a = analyze_position(pos, n_paths=n_paths)
        g, risk, dec = a["graph"], a["risk"], a["decision"]
        nodes = {n.id: n for n in g.nodes() if n.id != g.root_id}
        per.append({
            "id": pos["id"], "label": pos["label"], "kind": pos["kind"],
            "size_usd": pos.get("size_usd", 0),
            "verdict": dec["verdict"], "el": dec["el"], "carry": dec["carry"],
            "net_stay": dec["net_stay"], "exit_cost": dec["exit_cost"],
            "cvar95": dec["cvar95"], "dominant_path": dec.get("dominant_path", ""),
            "nodes": {nid: {"label": n.label, "kind": n.kind} for nid, n in nodes.items()},
            "transmission": {nid: risk.transmission.get(nid, 0.0) for nid in nodes},
        })

    shared = _shared_dependencies(per)
    heatmap = _heatmap(per, shared, top=10)
    ranking = sorted(per, key=lambda r: r["net_stay"])  # worst (most negative) first
    total_el_usd = sum(r["el"] * r["size_usd"] for r in per)
    total_usd = sum(r["size_usd"] for r in per)
    return {
        "per_position": per, "shared": shared, "heatmap": heatmap, "ranking": ranking,
        "totals": {"positions": len(per), "aum_usd": total_usd, "expected_loss_usd": total_el_usd,
                   "expected_loss_pct": total_el_usd / total_usd if total_usd else 0.0},
    }


def _shared_dependencies(per: list[dict]) -> list[dict]:
    index: dict[str, dict] = {}
    for r in per:
        for nid, n in r["nodes"].items():
            e = index.setdefault(nid, {"id": nid, "label": n["label"], "kind": n["kind"],
                                       "positions": [], "max_transmission": 0.0})
            e["positions"].append(r["id"])
            e["max_transmission"] = max(e["max_transmission"], r["transmission"].get(nid, 0.0))
    shared = [e for e in index.values() if len(set(e["positions"])) >= 2]
    kind_rank = {k: i for i, k in enumerate(_SHARE_KINDS)}
    shared.sort(key=lambda e: (-len(set(e["positions"])), kind_rank.get(e["kind"], 9),
                               -e["max_transmission"]))
    for e in shared:
        e["count"] = len(set(e["positions"]))
    return shared


def _heatmap(per: list[dict], shared: list[dict], top: int = 10) -> dict:
    # prefer the most-shared, highest-transmission non-chain deps for the columns
    cols = [e for e in shared if e["kind"] != "chain"][:top]
    col_ids = [c["id"] for c in cols]
    col_labels = [f"{c['label']}" for c in cols]
    rows, matrix = [], []
    for r in per:
        rows.append(r["label"])
        matrix.append([round(r["transmission"].get(cid, 0.0), 3) for cid in col_ids])
    return {"rows": rows, "cols": col_labels, "matrix": matrix, "col_ids": col_ids}
