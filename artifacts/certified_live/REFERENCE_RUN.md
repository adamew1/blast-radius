# Real live analysis: 2026-10-11

**Successful, bounded Morpho-only run.** This is not a successful combined
Pendle/Morpho run. Every financial response came from a real HTTP request. No mock,
historical response-cache value, altered clock, or relaxed freshness threshold was used.

## Supported position and workflow

- Morpho Hakutora USDC, Ethereum vault `0x974c8FBf4fd795F66B85B73ebC988A51F1A040a9`.
- Illustrative allocation: **$1,000,000**; not a wallet balance.
- Funded collateral dependency: cbBTC, market `0x64d65c9a2d91c36d56fbc42d69e979335320169b3df63bf92789e2c8883fcc64`.
- Discover rebuilt the graph from the selected vault and its current funded market.
- Attack applied a hypothetical 100% intrinsic cbBTC collateral shock.
- Collapse used incremental aggregate collateral shortfall divided by market supply.
- Rescue ran the existing constrained optimizer on its unchanged 5% Morpho grid.
- Prove reconstructed the scenario/candidates and audited the plan from the embedded
  observations offline, successfully.

## Source timestamps and freshness

All times UTC, **2026-10-11**. Validation occurred at **2026-10-11T03:33:47.416033+00:00**.

| Observation | Provider timestamp | Block | Age at decision | Limit | Result |
|---|---|---:|---:|---:|---|
| Vault allocation, total assets and net APY | 2026-10-11T03:25:47+00:00 | 26166506 | 480.416s | 900s | PASS |
| Canonical cbBTC/USDC lending-market state | 2026-10-11T03:33:35+00:00 | 26166545 | 12.416s | 900s | PASS |

Observation skew was **468 seconds**, within the 900-second limit.
Acquisition ran from **2026-10-11T03:33:45.457960+00:00** to **2026-10-11T03:33:47.409380+00:00**.

| Real request | Requested UTC | Received UTC |
|---|---|---|
| POST https://blue-api.morpho.org/graphql | 2026-10-11T03:33:45.458051+00:00 | 2026-10-11T03:33:46.343787+00:00 |
| POST https://blue-api.morpho.org/graphql | 2026-10-11T03:33:46.343929+00:00 | 2026-10-11T03:33:46.641971+00:00 |
| GET https://api-v2.pendle.finance/core/v1/1/markets/active | 2026-10-11T03:33:46.642098+00:00 | 2026-10-11T03:33:47.408125+00:00 |

The Pendle active list was used only for token identity discovery. No financially
material Pendle market metrics, swap quotes, token-decimals RPC checks or cash-leg
quotes were required or claimed in this Morpho-only run. SDK quote freshness was
therefore **not exercised**.

## Observed balances and yield

| Quantity | Observed value |
|---|---:|
| Vault total assets | $15,315,356.55 |
| Vault funded claim in cbBTC/USDC | $15,315,356.55 |
| Vault net APY | 3.81377918% |
| Market supply | $337,211,921.82 |
| Market debt | $303,956,741.01 |
| Market collateral value | $692,771,359.46 |
| Market available liquidity | $33,255,180.81 |

## Model result

| Quantity | USD |
|---|---:|
| Initial conditional scenario loss | 901,381.95 |
| Indicative reduction: 45% of holding | 450,000.00 |
| Residual conditional scenario loss | 495,760.07 |
| Assumed gas reserve: 2 bps | 90.00 |
| Assumed external-cash conversion reserve: 10 bps | 450.00 |
| Accounted loss | **496,300.07** |
| Manager's accounted-loss limit | 500,000.00 |
| Thirty-day foregone carry | 1,410.58 |
| Economic protection cost | 1,950.58 |
| Net capital released under assumptions | 449,460.00 |

Solver status: **optimal** over available candidates. Target met: **yes**.
Financial audit verified: **yes**. Historical freshness and receipt replay: **PASS**.

## Inputs that remain manual or assumed

The allocation, shock and mandate are hypothetical. cbBTC's Coinbase issuer
relationship is manually mapped, not a reserve attestation. Generic transmission
coefficients remain assumptions (the direct collateral shock uses the aggregate
shortfall rule). Immediate aggregate collateral recovery, unchanged residual
allocation proportions, 30-day linear carry, zero return on external cash, 2 bps
gas and 10 bps cash conversion are assumptions. Morpho capacity is a funded-claim
and shared-liquidity bound, not a certified withdrawal transaction. Borrower-level
liquidations, queues, permissions, execution delays and future liquidity are not
certified. No wallet was connected and no transaction was submitted.

**The result is an indicative model rescue, not an executable plan; fully_live=false
and executable=false.** Freshness passed at the decision time, not indefinitely.

## Unsupported scope in this attempt

The original ten-position book was separately retried at
2026-10-11T03:34:52.203599+00:00 and rejected: Risk inputs rejected: Stale or future 0x0367161b7cb23dfd03747dd3815d1c445b0437b648a6d50346249c6e7b92ff1b: age 1805.2s; maximum 900s.
Its other positions are not certified by this successful one-position receipt.

A separate real Pendle PT-wstETH probe at 2026-10-11T03:34:53.672573+00:00 returned provider
market timestamp 2026-10-11T03:00:00.000Z; it failed:
Stale or future Pendle PT-wstETH market data: age 2093.7s; maximum 900s. Thus this work does **not** establish a successful live Pendle
analysis or exact-size quote workflow.

To make the valid Morpho-only run possible, acquisition was corrected to fetch
selected vaults rather than unrelated catalog vaults when there is no direct PT
position. Direct PT books retain their eight-vault contagion scan. Raw vault and
allocation asset amounts were also requested alongside USD values. Freshness limits,
reconciliation tolerances, scenario formulas and optimizer rules were unchanged.

## Reproduce

Receipt: `artifacts/certified_live/hakutora_20261011_receipt.json`

Receipt SHA-256: `4bc6e93e81590279492b48844faebf8879724b2ad785acb301a3a07e7ccc2092`

```powershell
.venv/Scripts/python.exe scripts/verify_receipt.py artifacts/certified_live/hakutora_20261011_receipt.json
.venv/Scripts/python.exe scripts/run_live_analysis.py --positions hakutora-usdc --dependency token:ethereum:0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf
```

Replay verifies the recorded run at its original time without network. A new run
makes fresh network requests and can fail if observations no longer pass policy.


This report documents the original historical capture. The final release also contains `hakutora_release_20261011_receipt.json` and `hakutora_browser_20261011_receipt.json`; see `independent_audit.json` and the root JUDGE_GUIDE.md for their actual source times and changed results. No historical observation is relabelled fresh today.
