"""Describe each metric separately; a ROC-AUC win does not imply a PR-AUC win."""

def comparison_text(model: dict, baseline: dict) -> str:
    names = {"roc_auc": "ROC-AUC", "pr_auc": "PR-AUC", "brier": "Brier"}
    wins, other = [], []
    for key, label in names.items():
        better = model[key] < baseline[key] if key == "brier" else model[key] > baseline[key]
        (wins if better else other).append(label)
    def joined(items):
        return " and ".join(items) if len(items) < 3 else ", ".join(items[:-1]) + " and " + items[-1]
    text = f"Model edges out the base rate on {joined(wins)}" if wins else "Model does not improve on the base rate"
    if wins and other:
        text += f", not {joined(other)}"
    return text + "; base-rate priors remain the production backbone"
