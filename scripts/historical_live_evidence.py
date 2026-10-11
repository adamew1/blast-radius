"""Offline classification helpers for archived API receipts; no application UI."""
from app.live_data import live_receipt
from blast_radius.sources.live import FreshnessPolicy, LiveInputError, digest, timestamp, utc


def risk_data_status(status):
    """Distinguish the selected acceptance window from the strict live standard."""
    checks = [c for c in status["checks"] if c["kind"] == "risk"]
    max_age = max((c["age_seconds"] for c in checks), default=0)
    times = [c["observed_at"] for c in checks]
    skew = max(times) - min(times) if times else 0
    strict = FreshnessPolicy()
    delayed = max_age > strict.risk_seconds or skew > strict.max_skew_seconds
    return {"classification": "rejected" if not status["risk_usable"] else
            "delayed risk observations" if delayed else "fresh risk observations",
            "strict_15_minute_risk_passed": bool(status["risk_usable"] and not delayed),
            "maximum_observed_risk_age_seconds": max_age, "risk_timestamp_spread_seconds": skew,
            "selected_risk_age_limit_seconds": status["policy"]["risk_seconds"],
            "selected_risk_spread_limit_seconds": status["policy"]["max_skew_seconds"]}


def observation_receipt(run, analysis=None):
    rec = live_receipt(run, analysis)
    status = analysis["freshness"] if analysis else rec["freshness_at_capture"]
    rec["risk_data_status"] = risk_data_status(status)
    if rec["risk_data_status"]["classification"] == "delayed risk observations":
        rec["classification"] = "delayed protocol observations; indicative analysis, not verified fresh live data"
    elif not status["risk_usable"]:
        rec["classification"] = "rejected protocol observations; no verified current analysis"
    if getattr(run, "replay_context", None):
        rec["presentation_context"] = dict(run.replay_context)
        rec["classification"] = "historical replay of " + rec["risk_data_status"]["classification"] + "; not current live data"
    rec.pop("receipt_sha256")
    rec["receipt_sha256"] = digest(rec)
    return rec


def rejected_morpho_inputs(run, status):
    """Describe rejected identities from the captured data, without accepting them."""
    reasons = " ".join([status["risk_error"] or ""] +
                       [r["reason"] for r in status["rejections"] if r["kind"] == "risk"]).lower()
    if "stale or future " not in reasons:
        return []  # Balance/identity errors must not be described as old timestamps.
    selected = {p["id"] for p in run.positions}
    rows = {}
    # Native normalization can reject a price before its vault is added to the
    # run. The rejected provider response is still preserved as raw evidence.
    vaults = {}
    for record in getattr(run.client, "observations", []):
        response = record.get("response")
        data = response.get("data") if isinstance(response, dict) else None
        vault = data.get("vaultByAddress") if isinstance(data, dict) else None
        if isinstance(vault, dict) and isinstance(vault.get("address"), str):
            vaults[vault["address"].lower()] = vault
    vaults.update(run.vault_records)
    used_prices = getattr(run.client, "normalization", {}).get("prices", {})
    for p in run.catalog:
        vault = vaults.get(p.get("vault", "").lower())
        if not isinstance(vault, dict) or not isinstance(vault.get("state"), dict):
            continue
        state = vault["state"]
        inputs = [(p["id"], "vault", state)]
        assets = [vault.get("asset")]
        allocations = state.get("allocation")
        for allocation in allocations if isinstance(allocations, list) else []:
            if not isinstance(allocation, dict) or not isinstance(allocation.get("market"), dict):
                continue
            market = allocation["market"]
            mid = market.get("marketId", "")
            if isinstance(mid, str) and mid and allocation.get("supplyAssetsUsd"):
                assets.extend([market.get("loanAsset"), market.get("collateralAsset")])
                def symbol(key):
                    asset = market.get(key)
                    return asset.get("symbol", "unknown asset") if isinstance(asset, dict) else "unknown asset"
                market_state = market.get("state")
                inputs.append((mid, f"{symbol('collateralAsset')} / {symbol('loanAsset')} market",
                               market_state if isinstance(market_state, dict) else {}))
        if "morpho risk-token price " in reasons:
            for asset in assets:
                if not isinstance(asset, dict) or not isinstance(asset.get("address"), str):
                    continue
                address = asset["address"].lower()
                price = used_prices.get(address, asset.get("price"))
                inputs.append((address, f"{asset.get('symbol', address)} USD price",
                               price if isinstance(price, dict) else {}))
        for identity, label, observation in inputs:
            if identity.lower() not in reasons:
                continue
            row = rows.setdefault(identity, {"identity": identity, "input": label, "positions": [],
                                             "scope": [], "provider_time_utc": "Unavailable",
                                             "age_seconds": None, "max_age_seconds": run.client.policy.risk_seconds})
            if p["label"] not in row["positions"]:
                row["positions"].append(p["label"])
            scope = "selected holding" if p["id"] in selected else "PT contagion discovery"
            if scope not in row["scope"]:
                row["scope"].append(scope)
            try:
                observed = timestamp(observation.get("timestamp"))
                row["provider_time_utc"] = utc(observed)
                row["age_seconds"] = timestamp(status["checked_at"]) - observed
            except (LiveInputError, OverflowError, OSError):
                pass
    return list(rows.values())
