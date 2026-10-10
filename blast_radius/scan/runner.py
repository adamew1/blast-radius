"""Cached market universe -> production analysis -> auditable dollar exposures.

Amounts are gross vault TVL plus Pendle AMM liquidity. They can overlap economically.
For each canonical dependency, use production dominant-path transmission once per position.
Exposure is a stress-weighted notional, not expected loss or an additive reserve breakdown.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from datetime import datetime, timezone

from ..analyze import analyze_position
from ..config import ARTIFACTS, MANUAL, ROOT, load_config
from ..sources import morpho, pendle
from ..sources.cache import RAW_DIR


def universe(cfg: dict) -> tuple[list[dict], dict]:
    cid = cfg["chain_id"]
    vaults = morpho.vaults((cid,), first=cfg["morpho_first"])
    markets = pendle.markets_active(cid).get("markets", [])
    positions = []
    for v in vaults:
        size = (v.get("state") or {}).get("totalAssetsUsd") or 0
        if size >= cfg["morpho_min_tvl_usd"]:
            positions.append(dict(id=f"morpho-{v['address'].lower()}", kind="morpho_vault",
                                  label=v["name"], vault=v["address"], size_usd=size,
                                  chain="ethereum", chain_id=cid, vault_snapshot=v))
    for m in markets:
        size = (m.get("details") or {}).get("liquidity") or 0
        if size >= cfg["pendle_min_liquidity_usd"]:
            positions.append(dict(id=f"pendle-{m['address'].lower()}", kind="pendle_pt",
                                  label=f"Pendle {m['name']} · {m['expiry'][:10]}",
                                  market=m["address"], size_usd=size, chain="ethereum",
                                  chain_id=cid, market_snapshot=m))
    snapshot_times = {"morpho": [], "pendle": []}
    for path in RAW_DIR.glob("*.json"):
        packet = json.loads(path.read_text(encoding="utf-8"))
        body = packet.get("data")
        label = packet.get("meta", {}).get("label", "")
        if label == "morpho_vaults" and isinstance(body, dict) and (body.get("data") or {}).get("vaults", {}).get("items") == vaults:
            snapshot_times["morpho"].append(packet["cached_at"])
        if label == f"pendle_active:{cid}" and isinstance(body, dict) and body.get("markets") == markets:
            snapshot_times["pendle"].append(packet["cached_at"])
    cached_at = {kind: datetime.fromtimestamp(min(stamps), timezone.utc).isoformat()
                 for kind, stamps in snapshot_times.items() if stamps}
    return positions, dict(morpho_listed=len(vaults), pendle_active=len(markets),
                          source_cached_at=cached_at,
                          morpho_page_full=len(vaults) >= cfg["morpho_first"],
                          morpho_listed_tvl_usd=sum((v.get("state") or {}).get("totalAssetsUsd") or 0 for v in vaults),
                          pendle_active_liquidity_usd=sum((m.get("details") or {}).get("liquidity") or 0 for m in markets))


def _exit_estimate(p: dict) -> dict:
    # Scan ranking uses EL-carry, which does not depend on exit cost. Never pretend these
    # population-size estimates are executable quotes. Position tab retains SDK quotes.
    if p["kind"] == "pendle_pt":
        return dict(cost_pct=0.01, method="scan assumed exit cost",
                    detail="Assumed 1%; no executable quote for the entire AMM. Ranking uses EL minus carry.")
    v = p["vault_snapshot"]
    withdrawable = sum(min(a.get("supplyAssetsUsd") or 0,
                          ((a.get("market") or {}).get("state") or {}).get("liquidityAssetsUsd") or 0)
                       for a in ((v.get("state") or {}).get("allocation") or []))
    shortfall = max(0, 1 - withdrawable / p["size_usd"])
    return dict(cost_pct=0.0002 + 0.02 * shortfall, method="scan liquidity estimate",
                withdrawable_usd=withdrawable,
                detail="Allocation-capped available liquidity; 2% assumed haircut on shortfall.")


def analyze(p: dict, cfg: dict) -> dict:
    result = analyze_position(p, horizon_months=cfg["horizon_months"], n_paths=cfg["n_paths"],
                              seed=cfg["seed"], exit_info=_exit_estimate(p))
    g, risk, dec = result["graph"], result["risk"], result["decision"]
    if len(g.nodes()) <= 1:
        raise ValueError("resolver returned an empty graph")
    unknown = [n for n in g.nodes() if n.kind == "token" and
               (n.meta.get("unmapped") or not n.meta.get("mapped"))]
    deps = [dict(id=n.id, label=n.label, kind=n.kind,
                 transmission=risk.transmission.get(n.id, 0),
                 exposure_usd=p["size_usd"] * risk.transmission.get(n.id, 0),
                 expected_loss_usd=p["size_usd"] * risk.node_contrib.get(n.id, 0),
                 source=n.meta.get("source"), estimated=bool(n.meta.get("estimated")))
            for n in g.nodes() if n.kind in {"issuer", "token", "oracle"}]
    return dict(id=p["id"], label=p["label"], kind=p["kind"], size_usd=p["size_usd"],
                apy=result["apy"], el=risk.el, carry=dec["carry"],
                el_minus_carry=risk.el - dec["carry"], verdict=dec["verdict"],
                dominant_path=dec["dominant_path"], exit_estimate=result["exit"],
                fully_looked_through=not unknown,
                unmapped_tokens=[dict(id=n.id, label=n.label) for n in unknown],
                graph=g.to_payload(), dependencies=deps)


def aggregate(rows: list[dict], positions: list[dict], cfg: dict, meta: dict,
              elapsed: float, errors: list[dict], fingerprint: str) -> dict:
    totals: dict = {}
    for row in rows:
        for dep in row["dependencies"]:
            rec = totals.setdefault(dep["id"], dict(id=dep["id"], label=dep["label"], kind=dep["kind"],
                                                   exposure_usd=0, expected_loss_usd=0, positions=0))
            rec["exposure_usd"] += dep["exposure_usd"]
            rec["expected_loss_usd"] += dep["expected_loss_usd"]
            rec["positions"] += 1
    groups = {kind: sorted([d for d in totals.values() if d["kind"] == kind],
                           key=lambda d: -d["exposure_usd"]) for kind in ("issuer", "token", "oracle")}
    total = sum(r["size_usd"] for r in rows)
    eligible = sum(p["size_usd"] for p in positions)
    full = sum(r["size_usd"] for r in rows if r["fully_looked_through"])
    top3 = {d["id"] for d in groups["issuer"][:3]}
    # Explicit capped sum of transmission per position. Issuers can overlap in a stack;
    # this is a concentration index, not a claim of unique cash at risk.
    concentration = sum(r["size_usd"] * min(1, sum(d["transmission"] for d in r["dependencies"]
                                                 if d["id"] in top3)) for r in rows)
    opaque = defaultdict(lambda: dict(exposure_usd=0, positions=0, label=""))
    for r in rows:
        for n in r["unmapped_tokens"]:
            dep = next(d for d in r["dependencies"] if d["id"] == n["id"])
            opaque[n["id"]]["exposure_usd"] += dep["exposure_usd"]
            opaque[n["id"]]["positions"] += 1
            opaque[n["id"]]["label"] = n["label"]
    return dict(schema_version=1, generated_at=datetime.now(timezone.utc).isoformat(),
                snapshot_fingerprint=fingerprint, config=cfg, universe=meta,
                total_scanned_usd=total, eligible_usd=eligible, n_positions=len(rows),
                n_eligible=len(positions), exposures=groups,
                top3_issuer_concentration=dict(issuers=[d["label"] for d in groups["issuer"][:3]],
                                               weighted_usd=concentration,
                                               share=concentration / total if total else 0,
                                               method="Capped sum of top-three issuer dominant transmissions per position; overlapping index."),
                coverage=dict(fully_looked_through_usd=full, opaque_usd=total-full,
                              fully_mapped_positions=sum(r["fully_looked_through"] for r in rows),
                              fully_looked_through_pct=100*full/total if total else 0,
                              opaque_pct=100*(total-full)/total if total else 0,
                              eligible_scanned_pct=100*total/eligible if eligible else 0,
                              definition="Whole position counts as mapped only if every discovered token is mapped to declared depth. Not a reserve audit; dust/idle filtered by resolver."),
                top10=sorted(rows, key=lambda r: -r["el_minus_carry"])[:10], positions=rows,
                opaque_tokens=sorted([dict(id=k, **v) for k,v in opaque.items()], key=lambda d:-d["exposure_usd"]),
                errors=errors, scan_wall_seconds=round(elapsed, 3),
                limitations=["Ethereum only; listed Morpho V1 vaults and active Pendle markets above declared cutoffs.",
                             "Cache snapshot, not a current-price feed. Refresh explicitly to update.",
                             "Gross vault TVL + AMM liquidity can count the same underlying capital twice.",
                             "Dominant-path, pass-through-weighted exposures are model quantities, not unique dollars at risk; columns are not additive.",
                             "Manual issuer/wrapper links do not establish complete reserves or off-chain counterparties.",
                             "Morpho discovery follows funded collateral allocations; loan-asset issuer risk is outside this graph.",
                             "No allocation-sized executable Pendle quotes; ranking is expected loss minus carry."])


def run_scan(resume: bool = True) -> dict:
    cfg = load_config()["scan_config"]
    started = time.monotonic()
    positions, meta = universe(cfg)
    fingerprint = hashlib.sha256(json.dumps(dict(positions=positions, cfg=cfg), sort_keys=True).encode()
                                 + (MANUAL / "dependencies.yaml").read_bytes()
                                 + b"".join((ROOT / file).read_bytes() for file in (
                                     "blast_radius/scan/runner.py", "blast_radius/analyze.py",
                                     "blast_radius/discovery/resolvers.py", "blast_radius/discovery/engine.py",
                                     "blast_radius/risk/propagate.py", "blast_radius/risk/decision.py",
                                     "blast_radius/models/incidents.py", "blast_radius/models/severity.py",
                                     "blast_radius/models/passthrough.py"))).hexdigest()
    checkpoint = ARTIFACTS / "market_scan_checkpoint.json"
    state = json.loads(checkpoint.read_text(encoding="utf-8")) if resume and checkpoint.exists() else {}
    if state.get("fingerprint") != fingerprint:
        state = dict(fingerprint=fingerprint, rows=[], wall_seconds=0)
    done = {r["id"] for r in state["rows"]}
    errors = []
    for i, p in enumerate(positions, 1):
        print(f"[{i}/{len(positions)}] {p['label']} ${p['size_usd']:,.0f}", flush=True)
        if p["id"] in done:
            continue
        try:
            state["rows"].append(analyze(p, cfg))
            state["wall_seconds"] += time.monotonic() - started
            started = time.monotonic()
            tmp = checkpoint.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
            tmp.replace(checkpoint)
        except Exception as exc:
            errors.append(dict(id=p["id"], error=str(exc)))
            print(f"  FAILED: {exc}", flush=True)
    out = aggregate(state["rows"], positions, cfg, meta,
                    state["wall_seconds"] + time.monotonic()-started, errors, fingerprint)
    (ARTIFACTS / "market_scan.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out
