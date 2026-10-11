"""Portable source manifest and financial decision receipt."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from ..config import ROOT
from ..models.passthrough import PASS_THROUGH
from . import MODEL_VERSION

ASSUMPTIONS = [
    "One hypothetical intrinsic shock; scenario loss is not probability-weighted expected loss.",
    "Alternate paths to the same claim use the strongest channel; distinct funded vault allocations add.",
    "Aggregate collateral shortfall assumes immediate recovery at stressed collateral value; borrower-level liquidations are not simulated.",
    "Issuer, backing, oracle and liquidity transmission coefficients are modelling assumptions, not measured incident outcomes.",
    "Unmapped collateral and loan-asset issuer risks are not fully covered. Known issuers do not establish complete reserves.",
    "Withdrawals are bounded by snapshot funded allocations and shared market liquidity; withdrawal queues and executable transactions are not certified.",
    "All protection happens before the hypothetical failure; frozen indicative quotes do not guarantee future execution.",
    "Released capital is assumed transferred to external cash; conversion reserve is 10 bps and gas reserve is 2 bps, both assumptions.",
    "Remaining claims retain snapshot exposure proportions; market feedback, cash-transfer risk and FX movements are outside this model.",
    "Foregone carry uses nonnegative snapshot APY times 30/365; no reinvestment return is assumed.",
    "API observations and sourced manual mappings are distinguished from cached RPC observations; none are labelled live.",
    "The $10M book is an illustrative allocation to real instruments; judge-modified allocations are also hypothetical, not an observed wallet or managed fund.",
    "Evidence is a composite of individually timestamped captures, not an atomic block-aligned snapshot. Quote bundle captured_at is assembly time.",
    "Manual token-level oracle names are hypotheses about integrations, not verified deployed oracle contracts; market oracle addresses come from Morpho API observations.",
    "Discovery omits zero-funded and dust collateral allocations below the rounded 0.1% vault threshold. Missing paths are not evidence of safety.",
    "Aggregate recovery can understate borrower-level shortfalls at partial shocks; it pools collateral and excludes liquidation incentives and timing. It is modelled economic impairment, not a vault share-price forecast.",
    "PT claims pass underlying USD mark changes one-for-one at a fixed discount factor; a worthless underlying leaves no invented PT recovery. Other generic transmission coefficients remain assumptions.",
    "The optimizer minimizes protection cost subject to a manager-selected stress mandate. Plan-versus-hold break-even is not a marginal threshold or a globally optimal expected-return trading policy.",
]


def source_manifest() -> dict:
    records = []
    for path in sorted((ROOT / "data/raw").glob("*.json")):
        raw = path.read_text(encoding="utf-8").encode("utf-8")
        document = json.loads(raw)
        meta = document.get("meta", {})
        records.append({"path": str(path.relative_to(ROOT)).replace("\\", "/"),
                        "sha256": hashlib.sha256(raw).hexdigest(), "cached_at": document.get("cached_at"),
                        "source": meta.get("url"), "label": meta.get("label"),
                        "method": meta.get("method")})
    files = {}
    for name in ("data/manual/dependencies.yaml", "data/book/sample_book.json", "data/fire_drill/execution.json",
                 "data/fire_drill/catalog.json", "data/fire_drill/catalog_execution.json"):
        path = ROOT / name
        if path.exists():
            files[name] = hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    code = sorted((ROOT / "blast_radius").rglob("*.py"))
    code += [ROOT / "config.yaml", ROOT / ".streamlit/config.toml"]
    for path in code:
        files[str(path.relative_to(ROOT)).replace("\\", "/")] = hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()
    times = [r["cached_at"] for r in records if isinstance(r.get("cached_at"), (int, float))
             and ((r.get("label") or "").startswith(("pendle_active:", "pendle_data:", "morpho_vault:", "fire_drill_", "catalog_")))]
    payload = {"sources": records, "files": files,
               "presentation_evidence_window_utc": [datetime.fromtimestamp(t, timezone.utc).isoformat()
                                                     for t in (min(times), max(times))] if times else [],
               "timestamp_semantics": "cached_at is local retrieval time; price_updated_at is provider mark time; manual maps have file hashes, not an observation timestamp; captures are not synchronized",
               "hash_normalization": "UTF-8 text with line endings normalized to LF"}
    payload["bundle_sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return payload


def receipt(stress: dict, execution: dict, plan: dict | None, manifest: dict, bundle: dict,
            *, positions: list[dict] | None = None, catalog_mode: bool = False) -> dict:
    return {"created_at": datetime.now(timezone.utc).isoformat(), "model_version": MODEL_VERSION,
            "classification": "hypothetical pre-failure protection using frozen evidence",
            "scenario": stress, "plan": plan, "exit_candidates": execution,
            "quote_bundle": bundle, "evidence": manifest, "assumptions": ASSUMPTIONS,
            "coefficients": {**PASS_THROUGH, "pt_underlying_claim_override": 1.0},
            "receipt_schema": "blast-radius-decision-v3" if catalog_mode else
                              "blast-radius-decision-v1" if positions is None else "blast-radius-decision-v2",
            **({"portfolio": positions} if positions is not None else {})}
