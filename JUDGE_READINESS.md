# Final judge-readiness audit

**Verdict: PASS for the offline hackathon demonstration after critical corrections.**

**The original total-loss headline fails financial review and is superseded.** Its arithmetic reproduced, but a generic 0.95 coefficient invented 5% residual PT value after the underlying was assumed worthless. This audit corrected PT claims to transmit underlying USD mark changes one-for-one at a fixed discount factor. Model version: `single-shock-aggregate-recovery-v2-pt-parity`.

Audit date: **11 October 2026, Europe/Zurich**. Actual evidence capture times remain unchanged; they were not refreshed to the audit date. No wallet, trade or external publication was performed.

## PASS/FAIL matrix

| Check | Result | Evidence / scope |
|---|---|---|
| Original four headline amounts reproduce arithmetically | PASS | Reconstructed raw debt/supply, exact allocation weights, output values and carry; original model's PT loss was $950,000 |
| Original headline represents a defensible worthless-underlying PT scenario | **FAIL — fixed** | No evidence supported its $50,000 PT recovery; replaced with full underlying transmission |
| Corrected financial totals reproduce independently | **PASS** | Decimal raw-data reconstruction, no imports from the application's financial engine |
| Corrected rescue is cheapest on the available grid | **PASS** | Exhaustive 4,084,101 combinations; relaxed lower bound equals the independently resource-feasible solution |
| Shared liquidity / locks / unavailable quotes respected | **PASS** | Independent withdrawal funding and capacity audit; executable transactions are not certified |
| Hold-versus-plan economics explained | **PASS, conditional** | Whole-plan break-even and positive/negative expected net benefit under a supplied probability |
| Unconstrained optimal live trading decision or calibrated scenario probability | **FAIL / unsupported claim** | Neither is implemented or claimed; scenario-loss minimization alone cannot establish either |
| Evidence provenance and timestamp semantics | **PASS for traceability** | Original records, request/cache identities, provider marks and retrieval times inspected; hashes are not provider attestations |
| Genuine fresh re-verification of every historical observation | **NOT CLAIMED** | Archived block header re-fetched successfully; fresh decimals calls received HTTP 403; cached observations remain available |
| Numerical / regression checks | **PASS** | 31 tests, including PT parity, zero/monotonic shocks, overlap, exhaustive small examples, capacities, locks, solver states, quote availability and tampering |
| Full clean-start offline browser rehearsal | **PASS** | Discovery, shock, rescue, economic sign change, before/after, lock infeasibility, evidence tabs/paths, receipt download and recomputation, zero severity, reset |
| Native fallback and preserved research pages | **PASS** | Same financial engine; original research remains available, with corrected execution adapter |
| Timed two-minute fallback recording | **PASS** | Actual interactions and editorial captions; recording manifest records duration and video hash |

## Independently reconstructed amounts

All numbers below are conditional hypothetical calculations for the illustrative $10M allocation. They are not an observed fund loss or executed return.

| Amount | Original model, superseded | Corrected model |
|---|---:|---:|
| Conditional portfolio loss | $2,311,622.14 | **$2,361,622.14** |
| Protected accounted loss | $498,866.02 | **$498,999.85** |
| Economic protection cost | $21,753.37 | **$22,370.05** |
| Net capital released | $3,384,390.70 | **$2,682,047.49** |

The corrected original loss is the sum of:

| Position | Conditional loss |
|---|---:|
| PT-wstETH | $1,000,000.00 |
| Smokehouse USDT | $97,238.27 |
| Steakhouse USDT | $348,859.45 |
| Steakhouse ETH | $831,715.35 |
| Gauntlet USDC Prime | $83,809.07 |
| Other five positions | $0.00 under this selected scenario |
| **Total** | **$2,361,622.14** |

For each affected vault market, the independent audit reads the original Morpho response and computes:

`position size × funded market allocation / vault assets × incremental market shortfall / market supply`

`incremental shortfall = max(0, debt − collateral × (1 − shock)) − max(0, debt − collateral)`

At the headline direct wstETH zero-value shock, remaining collateral is zero; market impairment comes from the observed debt/supply ratio, under the disclosed recovery assumptions. At partial shocks, this aggregate formula is an approximation that can understate isolated borrower losses.

The new plan reduces PT-wstETH **70%**, Steakhouse ETH **100%** and Steakhouse USDT **100%**. Seven positions remain untouched. The residual is **$300,000 PT + $97,238.27 Smokehouse + $83,809.07 Gauntlet = $481,047.34**.

Independent reconciliations:

```text
accounted loss = 481,047.34 + 15,252.51 execution/gas + 2,700.00 conversion
               = 498,999.85
economic cost  = 15,252.51 + 2,700.00 + 4,417.54 foregone carry
               = 22,370.05
net capital    = 2,700,000.00 sold − 15,252.51 − 2,700.00
               = 2,682,047.49
```

Calculations retain full precision before display rounding. The entire quoted target has only **$1,000.15** of buffer. A worse actual fill or cash conversion can breach it. It is not a guaranteed execution outcome.

The standalone [independent audit script](scripts/audit_judge_readiness.py) verifies all 80 raw quote requests/outputs, decimal observations, integer input sizes, output asset marks, timestamps, candidates and selected liquidity funding. Its [machine-readable report](artifacts/judge_independent_audit.json) includes each contributing market's original balances and source hashes.

The enumeration omits unaffected positions because selling one cannot avoid this scenario's loss, adds nonnegative cost and consumes resources. It relaxes coupled shared liquidity when finding the lower bound; because the selected solution attains that bound and independently satisfies the actual capacities, the claimed optimum follows with capacities included. Locked PT-wstETH gives a relaxed lower bound of **$1,004,800**, attained by the verified minimum-loss plan; the $500,000 target is therefore infeasible.

## Belem's economic decision question

The app separates two questions:

1. **Given a binding manager risk mandate, what is the cheapest supported protection?** The MILP minimizes execution + conversion + foregone carry under the dollar-loss limit, discrete quote grid, locks and shared liquidity.
2. **Is paying for this plan economically justified relative to holding?** Under the stated binary, thirty-day scenario comparison, expected net benefit is `p × loss avoided − protection cost`.

For the corrected plan, avoided conditional loss is **$1,880,574.80** and economic cost is **$22,370.05**, giving **p* = 1.189533%**. At **p = 0.5%**, expected net benefit is **−$12,967.18**. At **p = 2%**, it is **+$15,241.44**. The browser audit verifies the sign change in the actual interface.

This answers the economic comparison conditionally. The manager's $500,000 mandate has no probabilistic meaning. The break-even probability applies to the whole chosen plan, not its marginal trades. A different expected-return optimizer could choose different reductions. The app does not estimate this exact scenario's probability, assert the plan is an unconditional trading recommendation, or combine unrelated historical priors with the shock to manufacture expected loss.

Foregone carry is approximated as nonnegative snapshot APY × 30/365, with zero cash yield and fixed exposure proportions. Event timing, state-dependent carry, other scenarios and preferences are excluded. These limitations are explicit in the README and evidence. The original Monte Carlo model remains separate research, not validation of this exact scenario probability.

The DoraHacks track page remained inaccessible during the audit. Judging alignment uses the Belem brief already supplied and quoted in the repository; official scoring weights, deadlines and submission requirements were not independently re-verified.

## Evidence provenance and timing

- Presentation data retrieval window: **2026-10-10 18:01:08–21:51:16 UTC**. Quote retrieval window: **21:49:04–21:51:16 UTC**. They are composite captures, not one atomic snapshot.
- Asset `price_updated_at` values are provider mark timestamps. `cached_at` is local retrieval time. Per-option `captured_at` can be assembly from a cache hit, not a new API observation. No timestamp was relabelled as live.
- Eight token decimal RPC observations are tied to block **`0x18f3e5b`** using original request/cache identities. The block header was independently re-fetched; its timestamp is **2026-10-10 21:48:47 UTC**. PT-reUSD is six decimals. Fresh follow-up calls for decimals returned **HTTP 403**; no successful live re-verification is claimed. [Raw follow-up record](artifacts/judge_rpc_block_check.json).
- The headline wstETH membership comes directly from observed Pendle underlying and Morpho collateral addresses. It does not require the generic manual oracle hypotheses or an incident prior. Lido identity and wrapper backing are separately sourced from documentation, including the [Lido wstETH contract documentation](https://docs.lido.fi/contracts/wsteth/).
- API market oracle addresses are observed protocol-reported fields. Generic manual token-level oracle names are now labelled **unverified integration hypotheses**, not verified contracts.
- Static manual mappings carry source URLs and file hashes, not fabricated observation dates. Unknown collateral and omitted loan-asset issuer/full backing risks are disclosed. Cached API/RPC files are genuine recorded inputs with reproducible identities; they are not cryptographically authenticated state proofs.

## Remaining financial boundaries a quant judge should see

1. **Cash conversion is required.** PT-wstETH exits return wstETH, not cash. Without a pre-failure second conversion, the claimed risk reduction fails. The 10 bps conversion reserve is an assumption, not a second-leg quote. Gas reserve is also assumed.
2. **Recovery is simplified.** Aggregate collateral netting can hide underwater borrowers at partial shocks, and liquidation incentives/timing are absent. The model measures economic impairment, not precise vault accounting recognition. Morpho's [liquidation documentation](https://docs.morpho.org/learn/concepts/liquidation/) describes borrower-level thresholds and incentives; the simplified model does not simulate them.
3. **Liquidity constraints are necessary bounds, not execution certification.** Queues, pauses, allowances, account ownership, transaction reverts, MEV and future state are not verified. Quotes are indicative recorded responses. Simultaneous exit market feedback is omitted.
4. **Coverage is incomplete.** The graph excludes zero-funded/dust collateral allocations under its declared threshold. Two positions contain unresolved collateral. Loan-asset issuer risk, full reserves, tranche waterfalls and FX remain incomplete. “Unaffected” means no modelled loss in this selected scenario, not safe in general.
5. **Other coefficients remain assumptions.** Strongest-channel aggregation avoids unjustified duplicate multiplication of one shared event but is not a full nonlinear joint-event model. Generic issuer/backing/oracle/liquidity sensitivities are not legally recoverable amounts or incident-calibrated probabilities.

These boundaries prevent claims of a live, calibrated, globally optimal trading system. They do not prevent a defensible demonstration of dependency discovery, conditional impact and constrained economic protection.

## Critical fixes made

- Corrected PT underlying transmission and versioned the deterministic model. Rebuilt every current headline, plan, screenshot, receipt and recording.
- Replaced the older research Pendle cost adapter's 18-decimal assumption, extra-fee addition and fabricated unavailable-fill estimate with exact-size frozen quoted output. Unsupported exits now produce **REVIEW**, not an invented stay/exit recommendation.
- Corrected older research Morpho liquidity to cap each market by its funded vault allocation; unfunded markets no longer supply fictitious withdrawal capacity.
- Preserved a genuine zero `netApy` instead of falling back to positive gross yield.
- Exposed composite evidence times, sample portfolio status, manual oracle hypotheses, PT cash-conversion requirements and whole-plan break-even scope.
- Prevented an unproved incumbent from being labelled a proved infeasible minimum in the comparison panel.
- Applied a consistent native dark theme so evidence tabs and JSON do not inherit low-contrast light-theme colours inside the terminal.

## Final artifacts and fallback

- [Submission README](README.md), [ready-to-paste submission](SUBMISSION.md), [exact pitch and cues](DEMO.md).
- [Unlocked receipt](artifacts/fire_drill_receipt.json), [browser-exported locked receipt](artifacts/browser_decision_receipt.json), [browser verification report](artifacts/fire_drill_verification.json).
- [120-second MP4 demonstration](artifacts/demo_video/blast-radius-two-minute.mp4), [original browser recording](artifacts/demo_video/blast-radius-two-minute.webm), [recording manifest](artifacts/demo_video/recording_manifest.json), and the six `FireDrill_*.png` [screenshots](artifacts/screenshots). MP4 removes 2.68 seconds of clean-launch pre-roll; no financial output is replaced.
- Primary: local app. First fallback: `http://localhost:8501/?fallback=1`, using the same engines with native controls. Second: local MP4 or WebM. Third: screenshots plus independent numerical report. Recorded artifacts are clearly labelled as recordings.

Prior research and the earlier presentation documentation are preserved in `docs/RESEARCH_README.md` and `docs/PREVIOUS_DEMO.md` for history. Their old execution/headline claims are superseded by this audit.
