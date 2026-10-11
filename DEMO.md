# Exact two-minute pitch

Use a 1500×1100 viewport or larger, at 100% zoom. Start from a clean launch or **Reset**. Default severity is 100% and accounted-loss limit is $500,000. Read the quoted text only; bracketed cues are actions. There are about 260 spoken words, leaving room for interaction at normal pitch pace.

## 0:00–0:12 — The illusion

[Show the initial ten cards.]

“Ten investments. Ten million dollars. You think you're diversified. But what if five investments are secretly the same bet? Let's ask the dependencies.”

## 0:12–0:30 — Discover

[Click **FIND MY WEAKEST POINT**. Point to wstETH and its five connections.]

“The graph automatically found wstETH underneath one Pendle position and four Morpho vaults. Different product names; shared collateral risk. This is an illustrative portfolio of real instruments. The discovery comes from observed market and allocation relationships.”

## 0:30–0:50 — Attack and collapse

[Click **SIMULATE FAILURE**. Let propagation finish.]

“Now give that dependency a hypothetical total-loss shock. Watch the actual paths transmit it: $2.36 million of modelled portfolio damage. We avoid counting overlapping paths twice. Lending losses come from collateral shortfalls, not simply crossing a liquidation threshold. This is conditional damage, not a forecast.”

## 0:50–1:20 — Rescue and economics

[Click **BUILD RESCUE PLAN**. At 0:55, scroll to the comparison. Point to accounted loss, cost and capital.]

“Before failure, cap accounted damage at half a million. The optimizer reduces three positions, leaves seven untouched, and reaches $499,000 including execution and conversion reserves. Economic protection costs $22,370, including foregone yield, and releases $2.68 million. Is that worth paying? Against holding, this plan breaks even above a 1.19 percent thirty-day scenario probability. That probability is an assumption, not our prediction.”

## 1:20–1:35 — Challenge

[Check **PT-wstETH** in locks. Click **BUILD RESCUE PLAN** again. Scroll back to the comparison.]

“Tell it this position cannot be sold. Now the target is infeasible: minimum accounted damage exceeds a million dollars. These are real constraints. The optimizer cannot promise a rescue the portfolio cannot support.”

## 1:35–2:00 — Prove and close

[Click **Show Me the Evidence**. Scroll to the evidence classification and native evidence drawer.]

“Here are the sources, capture times, assumptions and a reproducible receipt. Protection assumes converting exit proceeds to external cash before failure; these are frozen quotes, not guaranteed trades.

“In DeFi, your biggest risk isn't always the position you own. It's the dependency you didn't know you owned. Blast Radius discovers it, measures the damage, and finds the cheapest feasible way out.”

## Before going on stage

1. Install dependencies and optional browser tools in advance. Run tests, artifact rebuild, independent audit and receipt verification using the README commands.
2. Stop the existing application, start `python -m streamlit run app/Home.py`, and run `scripts/verify_fire_drill.py --record`. The audit run uses strict offline application mode and blocks external browser requests.
3. Rehearse the exact clicks in the recording. Keep the six screenshots and local MP4 accessible; no stream, download or internet should be needed on stage. The original WebM includes the clean-launch pre-roll; MP4 removes that pre-roll for a 120-second story.
4. Keep the target at $500,000 and use **PT-wstETH**, not another position, for the rehearsed lock challenge. Reset before the next pitch.

## Fallback hierarchy

- Custom component problem: open `http://localhost:8501/?fallback=1`. Click **Find My Weakest Point**, leave 100% severity, build rescue, then lock `pt-wsteth` and rebuild. Inspect evidence and download the same receipt format.
- Server or browser problem: play `artifacts/demo_video/blast-radius-two-minute.mp4` locally. The original `.webm` is also available. Say it is a recording of the verified build.
- Video problem: open `artifacts/screenshots/FireDrill_initial.png`, `_discovery.png`, `_collapse.png`, `_rescue.png`, `_locked.png`, `_proof.png` in order, and deliver this same script. Financial numbers can be checked in `artifacts/judge_independent_audit.json`.

## Skeptical-judge answers

- **Can I choose instruments outside the original ten?** Yes: the catalog includes PT-apyUSD, PT-USD3, Vault Bridge WETH and Vault Bridge USDC. Use **Remove** and **Add instrument** to build a new book, then Apply and repeat the same workflow. A $2.25M portfolio made entirely from these four instruments has three independently audited scenarios; the exact construction and limits are in [the catalog guide](docs/CATALOG_VALIDATION.md). This is a bounded Ethereum catalog, not wallet import or universal support.

- **Does this work beyond the prepared $10M book?** Open **Challenge this portfolio**. Ask the judge to resize PT-wstETH to $750,000 or remove a position with $0. Apply, rediscover, simulate and rebuild; point to the changed portfolio value, scenario loss and rescue. Quotes remain fixed dollar trades. For a sharper constraint test, resize PT-wstETH to $2M: captured quotes cover at most $1M, so full exit is unavailable. Reset restores the rehearsed book. Three modified books have separately audited optimal/infeasible outcomes; see [the review](docs/IMPROVEMENT_REVIEW.md).

- **Is wstETH going to fail?** No probability estimate or forecast is claimed. The ranking uses a standardized hypothetical shock; it ranks conditional damage, not likelihood.
- **Why is this the cheapest exit?** Four million combinations were independently enumerated. It is least cost on the available 5% grid for the stated stress mandate, not a globally optimal expected-return trade.
- **Does the economics justify acting?** Only under a supplied probability or binding risk mandate. At 0.5% assumed probability the plan has −$12,967 expected net benefit; at 2%, +$15,241. Its whole-plan break-even is 1.19%.
- **A PT exit returns wstETH, doesn't it?** Yes. Avoiding its risk requires the assumed second conversion to external cash before failure. That leg has a 10 bps reserve, not a verified quote. Leaving proceeds in wstETH would invalidate the claimed protection.
- **Are withdrawals executable?** The proposed reductions satisfy observed funded claims and shared liquidity capacities. Queues, pauses and transaction execution are not certified.
- **Does a PT retain value after its underlying becomes worthless?** No. The final audit corrected the generic 95% backing coefficient for PT claims. They now transmit underlying loss one-for-one at a fixed discount factor. That correction superseded the earlier $2.31M headline.
- **Are partial-shock lending losses exact?** No. Aggregate recovery can net healthy and unhealthy borrowers and understate losses. The simplified model omits incentives, timing and feedback. At the headline zero-value collateral shock, observed debt/supply determines market impairment under the stated assumptions.
- **Is all evidence on chain?** No. Protocol API responses, cached RPC decimals, sourced manual relationships and unverified integration hypotheses are distinctly labelled. Retrieval timestamps are not synchronized block timestamps; hashes prove reproducibility, not provider authenticity.
- **Is the older research model the same?** No. Its Monte Carlo incident priors and overlapping-path model are separate research. They do not estimate this scenario's probability.
