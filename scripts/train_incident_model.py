"""Train & honestly evaluate an incident-probability model vs the base-rate baseline.

Panel: one row per (protocol, year) for 2021-2025, built from the real /protocols + /hacks
datasets. Label = the protocol suffered an incident that year. Features are computed as-of the
start of each year where possible (age, prior incidents) — TVL is current (a documented
limitation / mild look-ahead). Time-based split (train <= 2023, test 2024-2025), isotonic
calibration, and a strict comparison to the category base-rate baseline on ROC-AUC, PR-AUC and
Brier. Writes artifacts/metrics.json (committed) and artifacts/incident_model.pkl (gitignored).

    python scripts/train_incident_model.py
"""
import datetime as dt
import json
import pathlib
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from blast_radius.config import ARTIFACTS  # noqa: E402
from blast_radius.sources import defillama  # noqa: E402
from blast_radius.models.evaluation import comparison_text

YEARS = [2021, 2022, 2023, 2024, 2025]
TRAIN_MAX = 2023
FEATURES = ["cat_code", "n_chains", "log_tvl", "age_years", "audits", "prior_incidents"]


def _year(ts) -> int:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).year


def build_panel():
    protocols = defillama.protocols()
    hacks = defillama.hacks()
    inc: dict[str, set] = defaultdict(set)
    for h in hacks:
        if h.get("defillamaId") is not None and h.get("date"):
            inc[str(h["defillamaId"])].add(_year(h["date"]))

    cats = sorted({p.get("category") for p in protocols if p.get("category")})
    cat_code = {c: i for i, c in enumerate(cats)}

    rows = []
    for p in protocols:
        cat, listed = p.get("category"), p.get("listedAt")
        if not cat or not listed:
            continue
        pid = str(p.get("id"))
        ly = _year(listed)
        audits = int(p["audits"]) if str(p.get("audits", "")).isdigit() else 0
        tvl = p.get("tvl") or 0.0
        n_chains = len(p.get("chains") or [])
        for y in YEARS:
            if y < ly:
                continue
            rows.append({
                "cat_code": cat_code[cat], "n_chains": n_chains, "log_tvl": np.log1p(max(tvl, 0.0)),
                "age_years": y - ly, "audits": audits,
                "prior_incidents": sum(1 for yy in inc.get(pid, ()) if yy < y),
                "year": y, "category": cat, "label": 1 if y in inc.get(pid, ()) else 0,
            })
    return rows, cat_code


def category_baseline(rows):
    """Baseline prediction = per-protocol-year incident rate of the category, learned on TRAIN only."""
    tot, pos = defaultdict(int), defaultdict(int)
    for r in rows:
        if r["year"] <= TRAIN_MAX:
            tot[r["category"]] += 1
            pos[r["category"]] += r["label"]
    overall = sum(pos.values()) / max(sum(tot.values()), 1)
    return {c: (pos[c] / tot[c] if tot[c] else overall) for c in tot}, overall


def main():
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
    try:
        from lightgbm import LGBMClassifier
        base = LGBMClassifier(n_estimators=300, max_depth=5, learning_rate=0.05,
                              class_weight="balanced", verbose=-1)
        model_name = "LightGBM"
    except Exception:
        from sklearn.ensemble import HistGradientBoostingClassifier
        base = HistGradientBoostingClassifier(max_depth=5, learning_rate=0.05,
                                              max_iter=300, class_weight="balanced")
        model_name = "HistGradientBoosting (sklearn)"

    rows, cat_code = build_panel()
    train = [r for r in rows if r["year"] <= TRAIN_MAX]
    test = [r for r in rows if r["year"] > TRAIN_MAX]
    Xtr = np.array([[r[f] for f in FEATURES] for r in train], float)
    ytr = np.array([r["label"] for r in train])
    Xte = np.array([[r[f] for f in FEATURES] for r in test], float)
    yte = np.array([r["label"] for r in test])

    clf = CalibratedClassifierCV(base, method="isotonic", cv=3)
    clf.fit(Xtr, ytr)
    p_model = clf.predict_proba(Xte)[:, 1]

    base_rates, overall = category_baseline(rows)
    p_base = np.array([base_rates.get(r["category"], overall) for r in test])

    def block(p):
        return {"roc_auc": round(float(roc_auc_score(yte, p)), 4),
                "pr_auc": round(float(average_precision_score(yte, p)), 4),
                "brier": round(float(brier_score_loss(yte, p)), 6)}

    metrics = {
        "model_name": model_name,
        "panel": {"rows_total": len(rows), "train_rows": len(train), "test_rows": len(test),
                  "train_positives": int(ytr.sum()), "test_positives": int(yte.sum()),
                  "test_prevalence": round(float(yte.mean()), 5)},
        "split": {"train_years": f"<= {TRAIN_MAX}", "test_years": f"> {TRAIN_MAX}"},
        "features": FEATURES,
        "model": block(p_model),
        "baseline_category_rate": block(p_base),
        "verdict": "model beats baseline" if roc_auc_score(yte, p_model) > roc_auc_score(yte, p_base)
                   else "model does NOT beat baseline — base rate remains production backbone",
        "notes": [
            "Heavy class imbalance: incidents are rare per protocol-year (see test_positives).",
            "TVL feature is current, not point-in-time (mild look-ahead) — documented limitation.",
            "Base-rate priors remain the live backbone; this model is reported for transparency.",
        ],
    }
    ARTIFACTS.mkdir(exist_ok=True)
    metrics["verdict"] = comparison_text(metrics["model"], metrics["baseline_category_rate"])
    (ARTIFACTS / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    import pickle
    (ARTIFACTS / "incident_model.pkl").write_bytes(pickle.dumps({"clf": clf, "cat_code": cat_code,
                                                                 "features": FEATURES}))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
