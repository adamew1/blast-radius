# Blast Radius: judge guide

Start in **Snapshot Mode**. All allocations and shocks are hypothetical. No
transaction is executed. This guide describes the final interface; older research
pages use a separate probabilistic model.

## A. Thirty-second explanation

Ten DeFi investments can hide one common dependency. Blast Radius unwraps Pendle
principal tokens and Morpho vault allocations, builds a dependency graph, and
calculates the portfolio damage from a selected hypothetical failure. It then
finds the cheapest supported reductions that satisfy a manager's loss mandate,
including costs and shared liquidity constraints. Judges can change the portfolio,
lock positions, inspect evidence and independently replay the decision.

## B. Two-minute demonstration

Install once with internet (Python 3.11+; validated here on 3.13):

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/python.exe -m streamlit run app/Home.py --browser.gatherUsageStats false
```

On macOS/Linux use `.venv/bin/python`. Open **http://localhost:8501**, use a
1500×1100 viewport, select **Snapshot Mode**, then **Reset** if needed. After
installation, this demonstration requires no internet, wallet, API key or secret.

| Time | Click | Expected result / what to say |
|---|---|---|
| 0:00 | Show initial portfolio | Ten real instruments, illustrative $10M allocation, frozen evidence. |
| 0:12 | **FIND MY WEAKEST POINT** | wstETH is discovered beneath five positions; conditional impact ranking, not a likelihood forecast. |
| 0:30 | Leave wstETH and 100%; **SIMULATE FAILURE** | $2,361,622.14 conditional loss (main display rounds dollars); inspect actual propagation paths. |
| 0:50 | Leave $500,000 mandate; **BUILD RESCUE PLAN** | Reduce PT-wstETH 70%, Steakhouse ETH 100%, Steakhouse USDT 100%; seven untouched. |
| 1:05 | Scroll to comparison | $498,999.85 accounted loss, $22,370.05 economic protection cost, $2,682,047.49 net released capital. All include disclosed assumptions. |
| 1:15 | Enter 0.5%, then 2%, in assumed probability | Expected net benefit changes from −$12,967.18 to +$15,241.44. Whole-plan break-even is 1.189533%; probability is supplied, never estimated. |
| 1:25 | Lock **PT-wstETH**, then **BUILD RESCUE PLAN** | Previous recommendation clears. Target infeasible; proved minimum accounted loss $1,004,800. |
| 1:40 | **Show Me the Evidence**; inspect tabs; **Download decision receipt** | API observations, RPC decimals, manual relationships and assumptions are distinguished. |

Verify the downloaded file (replace its path):

```powershell
.venv/Scripts/python.exe scripts/verify_receipt.py path/to/blast-radius-decision.json
```

Independent baseline reconstruction: `scripts/audit_judge_readiness.py`. It imports
no application financial engine, verifies 80 original exact quotes and enumerates
4,084,101 affected-position combinations. Financial amounts retain full precision
before display rounding. This is model protection **before** failure, with assumed
conversion to external cash; it is not a certified executable trade.

## C. Portfolio Challenge demonstration

**Reliable default for user-selected combinations:** stay in Snapshot Mode. Its
data is frozen, but portfolio selection, allocations, graph discovery, losses and
rescue are recalculated. If a portfolio is already configured in Live Mode,
click **Use frozen data for this portfolio** at the top. It keeps those holdings
and allocations, switches visibly to Snapshot Mode and discards previous plans.
Then run Find → Simulate → Build → Evidence. There is no API freshness check
because the evidence is explicitly historical. The separate **Use offline
Snapshot Mode** button retains the existing Snapshot session instead.

The fastest complete generalization takes about two minutes after the main demo:

1. **Reset**, then open **CHALLENGE THIS PORTFOLIO**.
2. **Remove** all ten rows. In the catalog picker, select and **Add instrument**
   for PT-apyUSD, PT-USD3, Vault Bridge WETH and Vault Bridge USDC.
3. Allocate respectively **500000, 750000, 500000, 500000** dollars.
4. **APPLY PORTFOLIO & REDISCOVER**, then **FIND MY WEAKEST POINT**.
5. Select **wstETH**, leave 100%, **SIMULATE FAILURE**, set limit **200000**, then
   **BUILD RESCUE PLAN**. Editing the mandate clears the previous recommendation.
6. Inspect evidence and download the receipt. Select **apyUSD**, then **USD3**,
   replay failure and rebuild for each. Keep the $200k mandate.
7. **Reset** restores the original $10M book, inputs and baseline result.

| 100% shock | Conditional loss | Accounted loss | Economic cost |
|---|---:|---:|---:|
| wstETH | $309,689.64 | $189,051.21 | $456.53 |
| apyUSD | $500,000.00 | $150,501.13 | $5,124.95 |
| USD3 | $750,000.00 | $151,799.56 | $9,221.25 |

All three optima are independently enumerated from raw data by
`scripts/audit_catalog.py`. A quick additional constraint challenge is a $2M
PT-wstETH holding: frozen quotes cover at most $1M. The engine cannot invent a
full-size exit. At most ten positive positions can be selected from the **14
admitted Ethereum instruments**, with $50k allocation steps and $2M per position.

## D. Live Mode demonstration

**Recommended final interface rehearsal (about one minute):**

1. Select **Live Mode** and click **Start live demo**. This explicitly chooses $1M
   Hakutora USDC, cbBTC, 100%, a $500k mandate and the 60-minute risk policy.
2. Read the source label. Fresh observations show their timestamps. Delayed data
   says delayed. If validation fails, the demo opens **HISTORICAL REPLAY**, using
   genuine saved API responses; say that it is recorded evidence, not fresh data.
3. **FIND MY WEAKEST POINT** → **SIMULATE FAILURE** → **BUILD RESCUE PLAN**.
   The graph and financial cards use the same presentation as Snapshot Mode.
   Expect a roughly 45% Hakutora reduction and around $496k accounted loss;
   fresh results can differ. Saved replay reproduces $496,292.74.
4. Inspect the three-way comparison and cost cards. **Show Me the Evidence** →
   **Download live observation receipt**. Explain that no transactions are sent.
5. Optional: lock Hakutora and rebuild to show honest infeasibility; unlock to
   restore the feasible plan. Severity or mandate changes clear the previous plan.

**Immediate recovery:** **Replay saved API run** works without internet and needs
no API check. It has a persistent historical label and original timestamps.
**Use offline Snapshot Mode** is the second fallback. For a component problem,
open `http://localhost:8501/?fallback=1`, select Live Mode and use the expanded
native controls. Portfolio/data settings and raw evidence are expandable; they
do not need to be opened for the main demonstration. A custom portfolio fetch
never silently replaces its holdings with the saved example.

Explain the three classifications explicitly:

- **Verified live analysis:** required observations passed freshness at the
  recorded decision time, calculations completed and the receipt replayed.
- **Indicative rescue:** optimization passed the mathematical constraints, but
  withdrawal execution, future fills and conversion into external cash are not
  certified. The receipt always has `executable=false` and `fully_live=false`.
- **Unsupported/stale:** required inputs failed validation; no current
  recommendation is certified. Choose the explicit Snapshot fallback.

Present the checked-in evidence first; historical replay needs no network:

```powershell
.venv/Scripts/python.exe scripts/verify_receipt.py artifacts/certified_live/hakutora_20261011_receipt.json
.venv/Scripts/python.exe scripts/verify_receipt.py artifacts/certified_live/hakutora_release_20261011_receipt.json
.venv/Scripts/python.exe scripts/audit_live_reference.py
```

The real HTTP runs certified **Hakutora USDC only**, with an illustrative $1M
holding and a hypothetical 100% cbBTC shock. Source: Morpho GraphQL. The first run,
at **2026-10-11 03:33:47 UTC**, used vault/market timestamps **03:25:47 / 03:33:35**:
loss **$901,381.95**, indicative reduction **45%**, accounted loss **$496,300.07**.
The release run at **03:44:59 UTC** used **03:35:23 / 03:44:23**: loss
**$901,381.52**, the same reduction, accounted loss **$496,299.83**. Freshness and
independent Decimal verification passed for both at their historical times.

A further real browser run at **03:57:10 UTC** used provider timestamps
**03:55:35 / 03:55:47**, passed freshness, and produced loss **$902,209.66** and
accounted loss **$496,755.31** with the same 45% indicative reduction. Its downloaded
receipt is `artifacts/certified_live/hakutora_browser_20261011_receipt.json`; the
independent audit verifies these captures. The recovery-button browser run at
**04:47:15 UTC** used **04:45:47 / 04:39:11** provider timestamps, passed freshness,
and produced loss **$901,379.25**, a **45% indicative reduction** and accounted loss
**$496,298.59**. Its replayable evidence is
`artifacts/certified_live/hakutora_recovery_20261011_receipt.json`.

For a fresh attempt: **Live Mode** → **Load $1M Hakutora live example** →
**Fetch fresh data & discover** → confirm **cbBTC** in **Attack dependency** →
leave 100% and $500k → **Calculate indicative model
rescue** → inspect timestamps and download the live receipt. Fresh values can
differ or fail validation; neither is a reason to loosen limits.

The example button explicitly replaces only the Live portfolio and clears the old
analysis; it does not fetch automatically. A failed request preserves the selected
portfolio. A stale Morpho rejection names the affected holding and collateral
market, shows its provider timestamp and age, and marks the validated timestamp
window as partial. The original ten-position book can still be selected manually;
its complete live coverage remains uncertified.

Strict certification policy: provider risk states and risk-token prices ≤900 seconds; execution USD marks, quote
request times and RPC block ≤120 seconds; risk skew ≤900 seconds; future tolerance 15 seconds. Freshness
is checked on actions, after solving and every 15 seconds in the UI. Captures are
asynchronous. SDK quote times are request times, not atomic on-chain state times.

The Live interface defaults to a user-requested **60-minute** risk age/spread
window. Data older than the strict standard is labelled **delayed**, including
any indicative rescue and receipt, and must not be presented as verified fresh
live analysis. Select **15** in **Maximum risk-data age (minutes)** for the strict
standard; **Load $1M Hakutora live example** selects it automatically. The wider
window never changes the two-minute execution-data limits or balance checks.

The original full-book attempt was rejected for stale Morpho state; a Pendle
market probe was also stale. **No successful live Pendle exact-size quote workflow
or complete ten-position live analysis is certified.** The active Pendle identity
list in a Morpho-only run is metadata, not a certified Pendle financial analysis.
The detailed evidence and model assumptions are in
[the historical run report](artifacts/certified_live/REFERENCE_RUN.md) and
[Live API limitations](docs/LIVE_DATA_LIMITS.md).

The subsequent native-unit correction completed a real **delayed risk-only**
ten-position browser analysis at **05:22:54 UTC**: wstETH 100%, **$2,359,706.70**
loss, risk timestamps **04:51:02–05:21:35 UTC**, accepted by the selected 60-minute
policy, **not** by the strict 15-minute standard. Eight vaults, 37 markets and 21
risk prices passed a separate native-unit audit. Incomplete manual coverage in
Steakhouse USDT and Yearn OG USDC blocked rescue. All 16 exact Pendle quote requests
were captured; complete fresh Pendle/rescue certification is still absent.

To demonstrate this bounded analysis, keep the original ten positions in Live
Mode, select **60**, then **Fetch fresh data & discover**. Explain the **delayed**
and **risk-only** warnings. Subsequent requests may reject as observations age.
For a delayed Hakutora demonstration, load the example, explicitly change its
reset **15** setting to **60**, then fetch and calculate. The recorded **05:24:19**
run produced **$901,368.61** loss and **$496,292.74** accounted loss with a 45%
indicative reduction. This is not new strict live certification. Exact evidence
and replay commands: [normalization audit](artifacts/certified_live/native_normalization_audit.json)
and [README](README.md#live-mode).

## E. Technical Q&A

**How is the graph discovered?** A breadth-first recursive resolver (maximum depth
8) expands selected instruments. Pendle supplies PT/underlying/AMM identities;
Morpho supplies each vault's funded collateral markets and deployed market oracle
addresses. Token addresses, market IDs, issuer IDs and chain IDs deduplicate nodes.
Edges point from a claim to its dependency; the animation reverses direction to
show failure propagation. Manual issuer/wrapper relationships are labelled.
Zero-funded and rounded <0.1% dust allocations are omitted. Discovery is bounded,
not universal reserve look-through.

**How do you avoid counting the same risk twice?** Alternate paths through one
claim use their strongest channel; separate funded vault allocations add.
Dependency columns and intermediate edge attributions are not additive dollars.

**What is a Pendle principal claim?** Its underlying-denominated maturity claim
transmits underlying USD mark loss one-for-one while the discount factor is held
fixed. A worthless underlying leaves no invented recovery. AMM, issuer and oracle
channels retain disclosed coefficients; they are assumptions, not legal recoveries.

**How does Morpho loss work?** For collateral shock `s`, incremental shortfall is
`max(0, debt − collateral × (1−s)) − max(0, debt − collateral)`. Divide by market
supply, bound to [0,1], then weight by the vault's funded allocation / total assets.
LLTV is metadata, not a substitute for supplier loss. Aggregate recovery pools
borrowers and can understate partial-shock losses; liquidations and feedback are
not simulated. Loan-asset issuer risk is incomplete.

**What does the optimizer prove?** A mixed-integer program chooses one available
candidate per position to minimize execution + conversion + 30-day foregone carry,
subject to residual loss + execution + conversion ≤ mandate, locks, funded claims
and shared market liquidity. Each shared market is counted once. Optimality applies
to the available discrete candidates. Timeout incumbents are labelled; a solver
failure does not prove infeasibility. A separate dollar-unit audit checks the plan.

**How are trade sizes and costs handled?** Snapshot PT quotes are exact captured
$50k–$1M dollar trades. Resizing changes the fraction, not the quote output or cost.
Live quotes use exact integer token input at checked marks/decimals. No quote is
interpolated, extrapolated or split. Output is valued once, including embedded
fees. Gas (2 bps), external-cash conversion (10 bps), linear carry and zero cash
return remain assumptions. PT exits return the underlying, which must be converted
before its failure. Morpho funded/shared-liquidity bounds do not certify queues,
pauses, permissions or executable transactions.

**Do you predict failure probabilities?** No. The manager chooses the stress
mandate. The binary plan-versus-hold comparison uses an assumed scenario
probability; break-even is cost / conditional loss avoided for the whole plan,
not a calibrated or marginal threshold. The research Monte Carlo model is separate.

**Can someone reproduce this?** Snapshot receipts hash the frozen inputs and model
files. Live receipts embed exact HTTP requests/responses and individual timestamps,
plus mappings, policy, portfolio, candidates and decisions. Replay is offline at
the historical time and requires matching model source. Hashes detect local
changes; they are not provider signatures. Independent scripts reconstruct raw
financial results without importing the production financial calculations.

## F. Demo recovery

- **Failed Live request / disconnected internet:** click **Use offline Snapshot
  Mode**, then **Reset**. Run the two-minute sequence. Never relabel historical
  evidence as current live data.
- **Custom component problem:** open **http://localhost:8501/?fallback=1**. Native
  controls use the same engine. Find the weakest point, use 100%, $500k and build;
  select `pt-wsteth` in **Lock positions** to reproduce infeasibility.
- **Dirty portfolio or scenario:** **Reset** restores the original book. Only
  applied Challenge allocations enter analysis; an invalid draft preserves the
  last valid applied portfolio and reports the error.
- **Corrupted session / blank browser:** open the URL in a new private window. If
  needed, stop Streamlit with Ctrl+C and run the launch command again; open a new
  browser session. No source-data regeneration is needed.
- **Application cannot launch on stage:** play the local
  `artifacts/demo_video/blast-radius-two-minute.mp4`; it is recorded evidence.
  If playback fails, use the `FireDrill_*.png` screenshots and the independent
  financial audit. The MP4 is silent; use [DEMO.md](DEMO.md) for narration.

Submission itself remains a team action. The repository records the DoraHacks URL;
official deadlines, required fields and judging weights could not be independently
verified. No submission or external publication is performed by these instructions.
