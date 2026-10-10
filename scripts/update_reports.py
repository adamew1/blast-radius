"""Regenerate pitch and README/submission figures from committed computed artifacts.

Use --check during verification to fail on stale generated sections.
"""
import argparse
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / "artifacts" / name).read_text(encoding="utf-8"))


def generated_sections():
    bt, scan = read("backtest_results.json"), read("market_scan.json")
    h, incl, fa = bt["headline"]["without_stream"], bt["headline"]["with_stream"], bt["false_alarms"]
    top, cov = scan["exposures"]["issuer"][0], scan["coverage"]
    kinds = {kind: [r for r in scan["positions"] if r["kind"] == kind] for kind in ("morpho_vault", "pendle_pt")}
    text = f"""## Track record

Excluding Stream: **{h['events_caught']}/{h['events_total']} advance catches**, **{h['misses']} misses**
(including {h['simultaneous_signals']} same-bar signals), **{h['median_lead_hours']:g}h median lead** among catches,
and **${h['total_saved_vs_naive_usd']:,} saved versus a naive 5% price-watcher** on $1M per pair.
Savings include every pair: a missed exit holds to its observed worst-14d mark, an unrealized
valuation rather than an executed sale. Both exit strategies assume 1% cost on sale proceeds.

Including the Stream development pairs: **{incl['events_caught']}/{incl['events_total']} catches**,
**{incl['median_lead_hours']:g}h median lead**, **${incl['total_saved_vs_naive_usd']:,} saved vs naive**.
Controls exclude Stream (no comparable 2024 data): **{fa['per_pair_year']:.3f} false alarms per pair-year**,
from **{fa['total_false_alarms']} alarms over {fa['total_pair_years']:.3f} observed pair-years**.
The descriptive stablecoin/CRV breakdown was added after observing controls:
{fa['by_upstream_kind']['stablecoin']['per_pair_year']:.3f} vs
{fa['by_upstream_kind']['volatile']['per_pair_year']:.3f} alarms per pair-year.
Missing intervals and incomplete 7-day-reference/14-day-follow-up windows are excluded, not treated as calm.

**Limits:** six non-development pairs share **{bt['n_triggers_out_of_sample']} distinct crises**;
selection was retrospective for data availability and visible breaks, not prospective holdout validation.
All exposure shares are estimated; CRV is a volatile stress proxy, not the exploited pool itself.
Prices use **4h buckets**, as-of alignment and bounded forward-fill; lead times and assumed exit
prices are uncertain within that sampling interval. The model's risk priors are current, not
historical point-in-time estimates. **Stream is the development case**; no ML early-warning
benchmark is claimed (`rule_vs_ml: null`). Parameters, every pair and sources:
[`artifacts/backtest_results.json`](artifacts/backtest_results.json).

## Market scan

**${scan['total_scanned_usd']:,.0f} gross TVL + AMM liquidity** across **{scan['n_positions']} positions**:
{len(kinds['morpho_vault'])} listed Ethereum Morpho V1 vaults ≥ $10M and
{len(kinds['pendle_pt'])} active Pendle markets ≥ $1M liquidity. Cached universe:
{scan['universe']['morpho_listed']} listed vaults and {scan['universe']['pendle_active']} active markets;
all qualifying positions analysed, {len(scan['errors'])} failures.

Largest shared issuer dependency: **{top['label']} — ${top['exposure_usd']:,.0f} transmission-weighted
notional across {top['positions']} positions**. Top-three issuer concentration index:
**{scan['top3_issuer_concentration']['share']:.1%}**, using a capped sum of dominant-path transmissions
per position. Whole-position mapping coverage is **{cov['fully_looked_through_pct']:.1f}%** to declared
issuer/base-asset depth; **{cov['opaque_pct']:.1f}% opaque** ({cov['fully_mapped_positions']}/{scan['n_positions']}
positions have no unmapped discovered token).

**Limits:** Ethereum only, listed V1 vaults/active markets only, thresholded cached snapshots.
Gross TVL plus pool liquidity can count the same economic capital twice. Transmission-weighted
notionals are model exposures, not unique dollars at risk; dependency columns are not additive.
Manual mappings do not establish complete reserves, validator operators, off-chain counterparties
or tranche waterfalls. Morpho discovery follows funded collateral, excluding loan-asset issuer
risk and idle/dust allocations. Scan ranking is EL minus carry; Pendle scan exit costs are assumed,
not executable quotes for entire pools. Source-cache dates, coverage and full results:
[`artifacts/market_scan.json`](artifacts/market_scan.json).
"""
    pitch = (
        f"Excluding Stream, the frozen rule caught {h['events_caught']}/{h['events_total']} selected historical pairs "
        f"before their downstream break, with {h['median_lead_hours']:g}h median lead and "
        f"${h['total_saved_vs_naive_usd']:,} saved versus a naive 5% price-watcher on $1M per pair. "
        f"There were {h['misses']} misses, including {h['simultaneous_signals']} same-bar signals, and "
        f"{fa['per_pair_year']:.3f} false alarms per pair-year ({fa['total_false_alarms']} across "
        f"{fa['total_pair_years']:.3f} observed pair-years). The Ethereum snapshot scans "
        f"${scan['total_scanned_usd']:,.0f} gross TVL plus liquidity across {scan['n_positions']} positions; "
        f"{top['label']} is the largest shared issuer dependency at ${top['exposure_usd']:,.0f} weighted notional, "
        f"with {cov['fully_looked_through_pct']:.1f}% mapped to declared depth. Caveats: retrospective "
        f"selection, only {bt['n_triggers_out_of_sample']} independent crises, estimated exposure shares, "
        "4h sampling and indicative exit prices, missed-exit savings marked at the observed worst 14-day "
        "hold value, incomplete control coverage, current risk priors, Stream as the development case, "
        "manual-map and reserve-depth limits, omitted Morpho loan-asset issuer risk, Ethereum-only scope, "
        "and overlapping gross capital. No early-warning ML benchmark is claimed. The separate incident "
        "model improves ROC-AUC and Brier, not PR-AUC; base-rate priors remain the production backbone."
    )
    return text, pitch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    section, pitch = generated_sections()
    start, end = "<!-- BEGIN COMPUTED REPORTS -->", "<!-- END COMPUTED REPORTS -->"
    block = f"{start}\n{section}\n{end}\n\n"
    outputs = {ROOT / "artifacts/pitch.txt": pitch + "\n"}
    for filename, anchor in (("README.md", "## Data sources"), ("SUBMISSION.md", "### How to run")):
        path = ROOT / filename
        source = path.read_text(encoding="utf-8")
        if start in source:
            result = re.sub(re.escape(start) + r".*?" + re.escape(end) + r"\n\n", lambda _: block, source, flags=re.S)
        else:
            index = source.index(anchor)
            result = source[:index] + block + source[index:]
        outputs[path] = result
    for path, contents in outputs.items():
        if args.check:
            assert path.exists() and path.read_text(encoding="utf-8") == contents, f"Stale report: {path}"
        else:
            path.write_text(contents, encoding="utf-8")
    print("Generated reports match artifacts." if args.check else "Updated README, SUBMISSION and artifacts/pitch.txt.")


if __name__ == "__main__":
    main()
