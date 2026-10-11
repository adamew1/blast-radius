# Blast Radius: final release report

**Verdict: PASS WITH LIMITATIONS.** Audited on 11 October 2026, Europe/Zurich.
Snapshot Mode is ready for the main demonstration. Live Mode is explicitly bounded
and fails closed; only Hakutora USDC has completed verified real-API analyses.
No new protocol, model, mathematical assumption or product feature was added during
this hardening pass. Previously developed Live Mode is included in the release.

## A. Scope and engineering audit

Inspected the actual source path from protocol clients and normalization through
recursive resolvers, graphs, single-shock propagation, candidates, MILP, dollar-unit
verification, UI state and receipts. The original $10M ten-position book, 14-instrument
Ethereum catalog, custom allocations, locks, shared resources, evidence, Snapshot
and Live modes remain intact.

Financial checks confirmed:

- Pendle quote sizing uses observed token decimals (including six-decimal PT-reUSD),
  integer token amounts and output USD marks. Fees embedded in output are not added
  again. Unsupported sizes are unavailable; holdings above quote coverage cannot
  extrapolate or split trades to fabricate exits.
- Edges point claim → dependency; loss propagates back to claims. Alternate paths
  through one claim overlap; separate funded allocations add. PT underlying loss
  transmits one-for-one at a fixed discount factor.
- Morpho impairment is incremental aggregate collateral shortfall / supply,
  weighted by funded allocation / vault assets. LLTV is not used as supplier loss.
  Withdrawals are bounded by funded claims and market liquidity; one market's
  resource is shared across vaults, using conservative frozen bounds or one
  canonical live observation.
- One candidate per position, position locks, loss mandate, funding equality and
  shared market constraints are enforced. Solver failure/timeouts are distinct
  from proved infeasibility. Solver output is independently checked in USD units.
- Execution/gas, conversion reserve and carry have separate accounting. The risk
  constraint excludes carry; the economic objective includes carry. Live and
  Snapshot use the same financial engine, with different explicitly sourced inputs.
- Provider state timestamps are separate from retrieval/quote request times. Live
  data never silently falls back to the historical response cache.

### Corrections made in this pass

| Original issue | Consequence | Safe correction | Newly executed verification |
|---|---|---|---|
| Snapshot terminal did not invalidate a plan when mandate/locks changed | Browser reproduced a $100k input beside the old $499k plan labelled “within your limit” | Commit changed controls to session state and clear plan/comparison/evidence; preserve scenario identity for the next solve | Actual browser checks that mandate and lock edits clear the prior plan and residual headline, then rebuild the expected optimal/infeasible result |
| A blur-triggered invalidation initially raced a direct Build click during the fix | Two catalog rehearsals dropped the first solve request | A direct Build carries the edited mandate in one event; blur commits other edits; scenario revision guards against an obsolete portfolio/dependency | Entire catalog browser rehearsal passes, including editing $200k and immediately clicking Build for all three scenarios |
| Risk observations could expire between the UI freshness check and analysis | `LiveInputError` from analysis could escape the fragment | Catch expiry, clear prior analysis and show a rejection with the Snapshot fallback still available | New AppTest regression forces expiry after a prior plan and verifies no exception or retained plan |
| Live lock IDs were not explicitly pruned after portfolio replacement | An obsolete lock could reach the optimizer's unknown-position check | Filter UI locks to the refreshed portfolio | New AppTest changes a locked PT book to Hakutora and verifies cleared locks and a valid new plan |
| Successful live evidence existed only in ignored runtime storage; old docs/video preceded Live Mode | A fresh checkout could not independently replay the claimed live success or follow the final interface | Commit selected historical receipts and rejected evidence; update guides, regenerate snapshot receipts/screenshots and re-record video | All 18 packaged receipts replay; staged-tree archive launches Snapshot and builds the baseline with HTTP calls forbidden; MP4 fully decodes and plays in Chromium |

No change was made to `shortfall_loss`, PT loss parity, exit arithmetic, pass-through
coefficients, optimizer objective, constraints, reserves, carry horizon, quote-size
rules, freshness thresholds or financial tolerances in this pass.

## B. Newly executed validation

These results were executed during this pass, not copied from earlier reports:

| Command / check | Actual result |
|---|---|
| `python -m unittest discover -s tests -v` | Initial 73/73 passed; final **75/75 passed**, zero failures. All previously reported tests are included; two new UI regressions were added. |
| `scripts/build_fire_drill_artifacts.py` | Rebuilt original scenarios, locked minimum, candidates and receipt from frozen inputs. |
| `scripts/audit_judge_readiness.py` | PASS; separate Decimal reconstruction, 80 raw quotes, 4,084,101 combinations. |
| `scripts/build_challenge_artifacts.py` + `scripts/audit_portfolio_challenge.py` | PASS; resized, removed and quote-limited books; 7,056 / 441 / 441 combinations. |
| `scripts/build_catalog_artifacts.py` + `scripts/audit_catalog.py` | PASS; 40 additional raw quotes, own decimals/marks and three new-book optima; 441 / 11 / 16 combinations. |
| `scripts/audit_live_reference.py` | PASS; independent Decimal reconstruction and exhaustive 21-candidate enumeration for each of three real Hakutora receipts. No application financial engine or solver imports. |
| `scripts/verify_receipt.py`, applied to every packaged receipt | **18/18 PASS**: 13 Snapshot decisions, three successful live captures and two rejected full-book captures. Replaying rejection verifies rejection, not a successful analysis. |
| `scripts/verify_fire_drill.py` | PASS from fresh server launch: baseline, node clicks, propagation, economics, before/after, edited controls, locks, evidence, downloads, zero shock, reset, native fallback and research pages. No external browser requests or uncaught JavaScript errors. |
| `scripts/verify_portfolio_challenge.py` | PASS: resizing/removal, singleton, zero shock, quote-limited infeasibility, invalid empty draft, Reset and native allocation controls. |
| `scripts/verify_catalog.py` | Final PASS after the documented UI event-race correction: actual Add/Remove construction, all three scenarios and receipts, dependency removal, Reset and native new-instrument addition. |
| `scripts/verify_release_live.py` | PASS with real APIs: Hakutora capture/attack/indicative rescue/download/replay; input invalidation; full-book stale rejection; immediate Snapshot recovery. |
| `scripts/verify_app.py` | Runs the preserved research artifact contracts and current full fire-drill browser rehearsal; also exercised in this pass. |
| `scripts/record_demo.py` | PASS: actual final-interface two-minute story; no external browser requests or JavaScript errors. |
| Editable installation and `pip check` | PASS; declared requirements installed without broken dependencies. Exact tested versions are recorded in `artifacts/release_environment.json`. |
| Staged-tree source archive | PASS: no untracked files needed; native Snapshot launch and baseline rescue with every `requests.Session.request` forbidden. See `artifacts/release_package_verification.json`. |
| MP4 verification | FFmpeg full decode PASS; Chromium playback PASS; H264, 1500×1100, 119.96 seconds. Source WebM and hashes retained. |
| Secret / artifact inspection | No tracked secret/env files or credential-pattern findings; public contract addresses remain evidence. MIT license and source attribution preserved. Removed the obsolete spare rehearsal WebM; no build/venv/browser cache is packaged. |
| `git diff --check` | PASS. |

Automated failure tests cover unavailable APIs, timeouts, HTTP/GraphQL errors, 429,
invalid JSON, stale/missing/future timestamps, inconsistent balances, missing marks,
decimal mismatch, quote failures, tampering and expiry after solving. A dedicated
browser outage simulation using a deliberately broken proxy was rejected by
automatic approval review without a detailed reason; it was not executed or claimed
as passed. Actual browser stale rejection and recovery passed. Initial Live browser
harness attempts also failed on native dropdown interaction; the final harness uses
ordinary keyboard selection and verifies the chosen cbBTC dependency in the receipt.

Machine-readable evidence: `artifacts/fire_drill_verification.json`,
`challenge_browser_verification.json`, `catalog_browser_verification.json`,
`release_live_browser_verification.json`, `release_receipt_verification.json` and
the independent audit files. Test output is retained locally as ignored
`artifacts/release_tests.log`.

## C. Financial consistency

The original book remains **$10,000,000**, wstETH, 100% intrinsic shock, $500,000
mandate. Every requested baseline amount reproduces independently to display cents:

| Quantity | Verified USD |
|---|---:|
| Original conditional loss | 2,361,622.14 |
| Residual conditional loss | 481,047.34 |
| Execution/mark shortfall including assumed gas | 15,252.51 |
| Conversion reserve | 2,700.00 |
| Accounted loss | **498,999.85** |
| Foregone 30-day carry | 4,417.54 |
| Economic protection cost | **22,370.05** |
| Net released capital | **2,682,047.49** |

Reductions: **70% PT-wstETH, 100% Steakhouse ETH, 100% Steakhouse USDT**.
Whole-plan break-even probability: **1.189533%**. Locking PT-wstETH makes the target
infeasible; the independently derived lower bound **$1,004,800** is attained by the
financially verified locked plan. It is therefore a proved model minimum.

The entirely new $2.25M book is PT-apyUSD $500k, PT-USD3 $750k, Vault Bridge WETH
$500k and Vault Bridge USDC $500k. At 100% shocks and a $200k mandate:

| Scenario | Conditional loss | Accounted loss | Economic cost |
|---|---:|---:|---:|
| wstETH | $309,689.64 | $189,051.21 | $456.53 |
| apyUSD | $500,000.00 | $150,501.13 | $5,124.95 |
| USD3 | $750,000.00 | $151,799.56 | $9,221.25 |

All three are independently verified discrete optima with funded/shared liquidity
checked. No headline values were hardcoded into production calculations.

## D. Actual Live Mode certification

**Supported successful scope: Ethereum Hakutora USDC only**, illustrative $1M;
hypothetical 100% cbBTC impairment; $500k mandate. All times below are UTC on
**2026-10-11**. Data source: real `https://blue-api.morpho.org/graphql` requests.
Pendle's active list is identity metadata only in these runs; no Pendle swap is
claimed. Each plan is **indicative and not executable**.

| Run | Decision time | Vault source time | Market source time | Loss | Accounted loss | Freshness |
|---|---|---|---|---:|---:|---|
| Earlier saved reference, replayed now | 03:33:47 | 03:25:47 | 03:33:35 | $901,381.95 | $496,300.07 | PASS historically |
| New CLI release capture | 03:44:59 | 03:35:23 | 03:44:23 | $901,381.52 | $496,299.83 | PASS at decision |
| New browser capture and download | 03:57:10 | 03:55:35 | 03:55:47 | $902,209.66 | $496,755.31 | PASS at decision |

All chose 45% reduction, met the mandate, replayed offline and passed a separate
Decimal audit. The original result was reproduced from its saved observations;
fresh API results were allowed to differ. Policy remains 900-second risk freshness
and skew, 120-second marks/quotes/RPC, 15-second future tolerance.

The fresh full-book browser request at **03:57:16 UTC** rejected a required
PT-sUSDS Morpho market state at **03:04:47 UTC** (age 3,149.9 seconds >900).
No recommendation was shown; Snapshot rescue worked immediately afterward. The
earlier full-book rejection and Pendle 03:00 market-data probe are retained.
**Complete ten-position live analysis and a live Pendle quote workflow remain
unverified.** No current freshness is implied by replaying any of these receipts.

Manual/assumed inputs remain allocations, shock and mandate; issuer/wrapper
relationships and token oracle hypotheses; transmission coefficients; immediate
aggregate recovery and unchanged residual allocation proportions; 2 bps gas,
10 bps cash conversion, linear 30-day carry and zero cash return. Queues,
permissions, transaction paths and future execution are uncertified.

## E. Limitations ranked by impact

1. **Execution correctness:** rescue is conditional mathematical protection.
   Conversion to external cash is assumed, quotes do not guarantee fills and
   Morpho withdrawals are uncertified. The baseline has only $1,000.15 target
   buffer; a worse fill can breach it. Never call this an executable strategy.
2. **Live demo reliability:** only Hakutora has passed real end-to-end analysis.
   Provider lags, outages, rate limits and Pendle timestamps can reject fresh
   attempts. Use Snapshot first; show historical Live receipts honestly.
3. **Risk coverage/model approximations:** bounded Ethereum catalog, incomplete
   issuer/backing/loan-asset risks, manual coefficients, dust/idle omissions and
   aggregate recovery that can understate partial borrower shortfalls. No
   calibrated failure probability, universal wallet support or atomicity.
4. **Submission requirements:** repository-supplied DoraHacks detail/build URLs
   were attempted and inaccessible. Deadlines, official scoring weights, required
   fields, team eligibility and upload limits remain unverified.
5. **Environment scope:** tested on Windows/Python 3.13/Chromium with recorded
   dependency versions. Installation requires internet; offline operation assumes
   dependencies are already installed. Other OS/version combinations were not
   separately certified.

## F. Exact demonstration and recovery

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/python.exe -m streamlit run app/Home.py --browser.gatherUsageStats false
```

Open **http://localhost:8501** → **Snapshot Mode** → **Reset** → **FIND MY WEAKEST
POINT** → wstETH / 100% → **SIMULATE FAILURE** → $500k → **BUILD RESCUE PLAN** →
lock PT-wstETH and rebuild → **Show Me the Evidence** → download receipt.

Failed Live request: **Use offline Snapshot Mode** → **Reset**. Custom component
failure: **http://localhost:8501/?fallback=1**. Session problems: new private browser
window; if necessary Ctrl+C and relaunch the command. Server unavailable: local MP4;
video unavailable: `FireDrill_*.png` screenshots and independent audit. Exact
Challenge/Live clicks, narration and Q&A: [JUDGE_GUIDE.md](JUDGE_GUIDE.md).

## G. Repository state

Intended submission branch: **main**, based on `f67ea9f`. The release commit includes
the previously uncommitted Live Mode work, minimal UI corrections, 75-test suite,
new audit/rehearsal scripts, judge guide/report, updated README/submission text,
refreshed Snapshot receipts/audits/screenshots/video and selected real Live evidence.
Financial engine formulas and frozen protocol inputs were preserved.

Use `git log -1 --format=%H` for the exact final commit identity and
`git show --stat HEAD` for the complete changed-file inventory. The final response
records that SHA; embedding a commit's own SHA in its contents is self-referential.
The release is committed locally on main. **No push, DoraHacks submission or
external publication is performed in this pass.**

## H. Submission checklist

- [x] Product scope frozen and financial/data/UI flow inspected.
- [x] Minimal corrections documented and tested; original baseline preserved.
- [x] Full suite, independent audits, all receipts and browser rehearsals executed.
- [x] Real Live certification bounded honestly; stale inputs reject safely.
- [x] Judge guide, README, limitations, submission copy and recovery instructions updated.
- [x] Final-interface backup video recorded, decoded and played; screenshots retained.
- [x] Frozen evidence, selected Live receipts and necessary code included in release.
- [x] Staged archive operates offline; no credentials or build dependencies bundled.
- [ ] Team: verify official requirements, deadlines, eligibility and required fields.
- [ ] Team: push the reviewed main commit and verify GitHub contains the same SHA.
- [ ] Team: submit the repository/branch, final demo video and required details on DoraHacks.
- [ ] Team: install dependencies and rehearse on the presentation laptop before travel.

No external submission or publication is authorized or performed by this report.

## Follow-up: native Morpho valuation correction, 11 October 2026

The release results above describe the original hardening pass. A subsequent
user-reported Live failure was traced to inconsistent cached USD display prices,
despite exact native supply/debt/liquidity reconciliation. Acquisition now derives
USD values from observed native integers, decimals and one timestamped price per
token. Financial formulas, original USD tolerances, shared liquidity constraints
and the optimizer are unchanged. Raw evidence and derivations are preserved in
versioned v2 receipts, with a separate adapter hash; old receipts still replay.

Newly executed validation: **89/89 tests**, baseline independent enumeration,
catalog and Portfolio Challenge audits, independent native balance/price audit,
independent 21-option Hakutora optimization reconstruction, all **10 packaged live
receipt replays**, and a real browser default fetch/download/Snapshot recovery
with no JavaScript errors. The original $2,361,622.14 / $498,999.85 Snapshot result
and independently audited alternative scenarios are unchanged.

Actual new API evidence: full ten-position wstETH risk analysis at **05:22:54 UTC**,
loss **$2,359,706.70**, source window **04:51:02–05:21:35 UTC**; selected 60-minute
policy passed, strict 15-minute policy failed. The result is **delayed risk-only**,
with rescue blocked by incomplete manual coverage. Sixteen exact Pendle quotes
were captured, without certifying a full fresh rescue. Delayed Hakutora/cbBTC at
**05:24:19 UTC** yielded **$901,368.61** loss, **45% indicative reduction** and
**$496,292.74** accounted loss; selected policy passed and strict certification
failed. A strict request was safely rejected for stale vault state.

Detailed cause, consequences, fix and independent checks:
[Live limits](docs/LIVE_DATA_LIMITS.md#native-unit-correction-2026-10-11-0522-utc).
Exact observations and timestamps:
[native audit](artifacts/certified_live/native_normalization_audit.json).
Readiness remains **PASS WITH LIMITATIONS**; no execution or publication is claimed.

## Follow-up: shared Live interface and demo recovery, 11 October 2026

Live Mode now uses the Snapshot terminal for graph discovery, hypothetical shocks,
loss cards, rescue comparisons and evidence. Advanced settings and raw JSON are
collapsed. **Start live demo** explicitly selects the $1M Hakutora/cbBTC example
and requests new API data. If that example cannot pass validation, it opens a
verified saved API run with a persistent **HISTORICAL REPLAY** label. Custom
portfolio failures preserve their holdings and offer explicit recovery choices.
Saved replay works offline, preserves the original observation timestamps and
records its parent receipt and historical decision time in new receipts. Neither
saved replay nor indicative rescue is labelled executable or fully live.

The previous Live interface exposed technical JSON instead of the five-stage
presentation. Its replacement changes presentation and recovery only. Financial
source files and the acquisition adapter are unchanged. Changes to portfolio,
dependency, severity, locks or mandate clear the previous plan. Duplicate terminal
events are guarded so rapid input cannot leave controls waiting indefinitely.
Replay receipts are independently checked against their packaged parent; changing
their historical flag to claim fresh data is rejected.

Newly executed validation: **92/92 tests**, **11 packaged receipt replays**,
independent native-unit/Decimal reconstruction and exhaustive 21-option Hakutora
optimization audit. A real Playwright browser rehearsal passed all five stages,
receipt download/replay, saved offline replay, locks and infeasibility, 25% severity,
reset and original Snapshot recovery, with **zero JavaScript errors**. No API mocks
were used for that browser run.

The browser obtained fresh Hakutora observations at **05:57:05 UTC**. Provider
timestamps: vault **05:55:47**, market **05:51:11**, USDC/cbBTC prices **05:53:58**.
The observations met the strict 15-minute standard at that decision time, despite
the selected 60-minute policy. Conditional loss **$901,352.27**; indicative reduction
**45%**; accounted loss **$496,283.75**. Actual withdrawal, gas and external-cash
conversion remain unverified assumptions. This certifies Hakutora only.

Evidence: [browser report](artifacts/live_ui_browser_verification.json),
[independent audit](artifacts/certified_live/live_ui_independent_audit.json),
[receipt](artifacts/certified_live/hakutora_live_ui_20261011_receipt.json),
[interface preview](artifacts/live_ui_preview.png). Current demonstration and
recovery instructions are in [JUDGE_GUIDE.md](JUDGE_GUIDE.md#d-live-mode-demonstration).
The previously recorded video predates this interface update; use the application
for the final Live demonstration. Readiness remains **PASS WITH LIMITATIONS**.

## Follow-up: portfolio-preserving frozen recovery

For custom-portfolio demonstrations, Snapshot Mode remains the reliable default:
observations are fixed while allocations, discovery, stress and optimization are
recalculated. **Use frozen data for this portfolio** now transfers the current
Live selections, dollar allocations and scenario settings into Snapshot Mode,
clears previous plans and uses frozen evidence exclusively. The existing generic
Snapshot fallback still retains its prior Snapshot session. Catalog boundaries,
exact-size quotes, shared liquidity and financial calculations are unchanged.

Two confusing validation messages were corrected. Off-grid allocations now name
the instrument and suggest the adjacent valid $50k amounts without changing the
entry. A stale native token price can fail normalization before the vault enters
the normalized run; the rejection inspector now reads the preserved raw response
to identify that vault, token and provider timestamp. The reported 4,737.9-second
failure was WOUSD collateral in Yearn OG USDC, legitimately outside the selected
3,600-second window. No price was fabricated and no freshness limit was extended.
Changing or invalidating allocations clears any previous model plan immediately.

Newly executed: **95/95 tests**, including the exact five-position $1M portfolio
from the user's screenshot transferred and optimized with network requests
forbidden. Browser reproduction and receipt verification are available through
`scripts/verify_frozen_portfolio.py`. This approach supports arbitrary combinations
within the admitted catalog and existing allocation limits; it does not import
arbitrary wallets or claim fresh or executable trades.
