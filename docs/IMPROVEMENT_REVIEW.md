# Submission improvement decision

**Catalog extension:** the allocation-only scope assessed below has since been extended to a validated 14-instrument catalog with dynamic Add/Remove controls. [Catalog admission, independent validation and limits](CATALOG_VALIDATION.md) supersede the ten-instrument scope and 40-test count below. The four-feature prioritization remains unchanged; only Challenge Mode was implemented.

**Implement Portfolio Challenge Mode only.** It addresses the prepared-book objection directly: a judge chooses allocations, then the same discovery, stress and optimization calculations produce a different decision. The original Discover → Attack → Collapse → Rescue → Prove sequence and default $10M allocation remain available through Reset.

## Assessment in the requested priority order

| Feature | Judge impact | Financial correctness requirements | Implementation effort | Risk to validated demo | Decision |
|---|---|---|---|---|---|
| **1. Portfolio Challenge Mode** | Very high: the judge supplies the input; membership, sizes and concentration change ranking, damage and feasible protection. Strongest direct evidence of generality. | Match quotes by instrument and **absolute trade amount**, recompute exit fractions, preserve original outputs/costs, rebuild funded/shared liquidity constraints, invalidate old plans, and reproduce the modified portfolio in receipts. Bound the supported universe. | Medium: allocation validation, candidate adapter, state/cache handling, dynamic presentation and receipt reproduction. | Medium before controls; contained by unchanged stress/optimization algorithms, bounded inputs, a collapsed editor and baseline regression/browser checks. | **Implemented and independently verified.** |
| **2. Protection Efficient Frontier** | High: answers how much additional protection costs; useful portfolio-manager decision support. Shows generality across mandates, less directly across portfolios. | Use **accounted** loss limits consistently; minimize execution + conversion + carry separately at each limit with locks/shared capacities. The discrete frontier is stepped; sold capital need not be monotonic between different optimal plans. Include a proved minimum attainable endpoint; distinguish unresolved solves from impossible targets. | Medium: repeated optimization, status-aware visualization, endpoints, and independent optimality checks across limits. | Low to medium: reuses the engine, but increases latency and proof scope. A smooth interpolated frontier would overstate executable choices. | Deferred. Good next analytical improvement after submission. |
| **3. Rescue Robustness** | High with quant judges: exposes how little execution headroom a successful plan may have. | Evaluate the **fixed recommended plan** under smaller capacities, higher costs and adverse conversion; identify infeasible withdrawals and target breaches. Reoptimizing sensitivity cases answers a different question. Haircuts and cost multipliers are assumptions, never executable quote evidence. | Medium: assumption scenarios, fixed-plan feasibility/economic checks, and clear evidence classification. | Medium: easy to imply stressed fills are quoted or conversion is guaranteed. The default plan has only $1,000.15 quoted target headroom. | Deferred. Existing conversion/queue/slippage limits stay explicit. |
| **4. One-click Mathematical Proof** | Medium to high: makes credibility easier to inspect, but overlaps with actual graph-path inspectors, evidence tabs, receipts and the independent audit already present. | Use selected numerical flows and actual quote/resource records. Lending shortfalls are nonlinear; multiplying every path coefficient is not generally a proof. Intermediate attributions are not additive dollars at risk. Show costs, locks and shared resource funding. | Low to medium for a concise visual; medium for full nonlinear derivations and accessible inspection. | Low if read-only; duplicating or oversimplifying evidence can introduce contradictions. | Deferred. The current proof workflow remains intact. |

Effort and impact are engineering judgments from this repository, not estimates of official judging weights.

## Submitted scope and boundaries

The editor supports the ten frozen Pendle/Morpho instruments, each at **$0–$2M in $50,000 increments**. Zero removes a position; an empty book is rejected. A changed book rebuilds discovery/ranking, losses, exits and liquidity constraints. Earlier plans, comparison results and evidence views are cleared; removed positions are removed from locks. The selected dependency is repaired if it no longer exists. Single-position books work without inventing a shared dependency. Severity and the manager's loss mandate remain explicit user assumptions.

Pendle candidates use the captured **$50k–$1M absolute amounts**, filtered to fit the holding. A $750k holding has fifteen captured nonzero candidates; a $2M holding has twenty and can sell at most half. Each retains its original output evidence, mark shortfall and raw cache key. There is no scaling of quote outputs, interpolation, extrapolation or summing quotes to invent a larger executable trade. Missing quotes and instrument identity mismatches cannot supply candidates. Morpho reductions retain a 5% holding grid with unscaled snapshot funded claims and market capacity shared across vaults.

Gas and external-cash conversion remain assumed reserves; frozen quotes and Morpho bounds do not certify future fills, transactions or queues. This demonstrates allocation generality within the supported frozen universe, not arbitrary instrument discovery, live execution or out-of-sample predictive validation. Optimality applies to available discrete candidates, not every possible trade size.

Version 2 receipts embed the modified portfolio. Verification rebuilds it from supported identities, recomputes stress/candidates and checks the frozen quote bundle. Version 1 original-book receipts remain supported. The deterministic stress formulas and MILP objective/constraints were not changed.

## Verification and submission gate

The full suite contains **40 passing tests**, including the original 31. New regressions cover exact-size quote reuse, missing quotes, identity mismatches, removal, liquidity conservation, singleton/zero stress, input validation, altered receipts, quote-limited infeasibility and unchanged baseline headlines.

The separate [Decimal audit](../scripts/audit_portfolio_challenge.py) imports neither the financial engine nor its solver. It reconstructs stress and candidate economics from raw protocol responses, verifies withdrawal funding/shared capacities, and enumerates relaxed candidate combinations. Each verified plan attains that independent bound, establishing the stated optimum with capacities included. This is independent implementation using the same frozen observations, not independent validation of the modelling assumptions.

All cases use a 100% intrinsic wstETH shock and a $500,000 accounted-loss limit:

| Modified portfolio | AUM | Conditional loss | Accounted loss | Economic protection cost | Independent result |
|---|---:|---:|---:|---:|---|
| PT-wstETH $750k; Steakhouse ETH $500k; Steakhouse USDT $1.25M; PT-sUSDe $1M | $3,500,000 | $1,601,931.99 | $499,644.43 | $9,383.44 | Optimal; 7,056 combinations |
| Same book with PT-wstETH removed | $2,750,000 | $851,931.99 | $498,962.96 | $1,033.13 | Optimal; 441 combinations |
| PT-wstETH $2M; Steakhouse ETH $500k; PT-sUSDe $1M | $3,500,000 | $2,415,857.68 | $1,027,448.98 minimum | $29,816.19 at minimum loss | Target infeasible; 441 combinations |

The original independent audit still enumerates **4,084,101** combinations and verifies **$498,999.85 accounted loss**, **$22,370.05 economic cost** and **$2,682,047.49 released capital** for the default book.

Both browser rehearsals block external requests. The original covers the entire pitch, economics, locks, proof/receipt, reset, native fallback and every research page. The challenge rehearsal covers edits, removal of the selected dependency, singleton books, zero shock, quote-limited infeasibility, empty-book rejection, Reset followed by the original rescue, and native resizing. Continuing after Reset exposed an acknowledgement bug; Reset now preserves the event acknowledgement so the next demonstration can proceed.

Reports: [original browser rehearsal](../artifacts/fire_drill_verification.json), [challenge browser rehearsal](../artifacts/challenge_browser_verification.json), [challenge independent audit](../artifacts/challenge_independent_audit.json), [original independent audit](../artifacts/judge_independent_audit.json).

Reproduce after installing the existing dependencies and optional Playwright browser:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe scripts/build_fire_drill_artifacts.py
.venv/Scripts/python.exe scripts/audit_judge_readiness.py
.venv/Scripts/python.exe scripts/verify_receipt.py
.venv/Scripts/python.exe scripts/build_challenge_artifacts.py
.venv/Scripts/python.exe scripts/audit_portfolio_challenge.py
# With the local Streamlit application running:
.venv/Scripts/python.exe scripts/verify_fire_drill.py
.venv/Scripts/python.exe scripts/verify_portfolio_challenge.py
```

Only Challenge Mode is included. A financial invariant failure or failed full demo rehearsal is a reason to omit the enhancement; the other three features do not enter the submission by default.
