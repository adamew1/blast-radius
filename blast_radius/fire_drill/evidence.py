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
    for name in ("data/manual/dependencies.yaml", "data/book/sample_book.json", "data/fire_drill/execution.json"):
        path = ROOT / name
        if path.exists():
            files[name] = hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    code = sorted((ROOT / "blast_radius/fire_drill").glob("*.py"))
    code += sorted((ROOT / "blast_radius/discovery").glob("*.py"))
    for path in code:
        files[str(path.relative_to(ROOT)).replace("\\", "/")] = hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()
    payload = {"sources": records, "files": files,
               "hash_normalization": "UTF-8 text with line endings normalized to LF"}
    payload["bundle_sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return payload


def receipt(stress: dict, execution: dict, plan: dict | None, manifest: dict, bundle: dict) -> dict:
    return {"created_at": datetime.now(timezone.utc).isoformat(), "model_version": MODEL_VERSION,
            "classification": "hypothetical pre-failure protection using frozen evidence",
            "scenario": stress, "plan": plan, "exit_candidates": execution,
            "quote_bundle": bundle, "evidence": manifest, "assumptions": ASSUMPTIONS,
            "coefficients": PASS_THROUGH,
            "receipt_schema": "blast-radius-decision-v1"}
