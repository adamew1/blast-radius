# DoraHacks BUIDL — ready-to-paste

**Event:** BSA EPFL · The Hackathon — **Belem Capital track** (DeFi Risk Dependency Challenge)
**Submit at:** https://dorahacks.io/hackathon/bsa-the-hackathon/build
**Hard requirement:** a public Git repo link (fill in after pushing). Demo video is recommended, not required.

---

### Project name
Blast Radius

### Tagline (one line)
Find hidden DeFi dependencies, simulate failure propagation, and compare stay/exit decisions — with historical misses, false alarms and Ethereum coverage shown openly.

### Description (paste into the BUIDL body)
On-chain positions carry risk that lives in their **dependencies** — the settlement chain, the underlying yield source and its issuer, the oracle, the AMM that prices and exits it, and the lending markets that hold it as collateral. When one of these fails, a portfolio manager doesn't just need an alert; they need to know **how the failure propagates to their position** and whether the expected loss justifies exiting despite slippage.

**Blast Radius** is a working Python engine + Streamlit dashboard that does exactly this:

1. **Recursive dependency discovery** — a Pendle PT or Morpho vault is unwrapped layer by layer from cached DefiLlama / Pendle / Morpho data. Issuer, some oracle and backing links come from a sourced manual map, labelled in the UI.
2. **Monte-Carlo failure propagation** — base-rate incident probabilities and severity priors propagate up the graph to give Expected Loss, CVaR-95 and the dominant risk path. Each dependency type uses a flat coefficient (oracle **0.70**); **LLTV is displayed in labels only**, with no liquidation threshold wired into propagation.
3. **A real stay/exit decision** — expected loss over the horizon is compared against the real cost of exiting (Pendle price-impact quotes / Morpho withdrawable liquidity) to return STAY / REDUCE / EXIT with a plain-English reason.

**Portfolio mode** finds dependencies shared across a book of 10 positions ("5 of 10 depend on Lido"), shows a position×dependency exposure heatmap, and ranks actions.

**The development demo** replays **Stream Finance → Elixir deUSD** on real daily DefiLlama prices and a sourced reconstructed graph. It flips to EXIT on **Nov 4**, while sdeUSD's sampled price is $1.07, three daily labels before its break. The **99.7%** figure is a gross price comparison before costs. Pre-break REDUCE follows from zero carry. The rule was built knowing Stream's outcome; Stream is excluded from the primary backtest headline.

The incident model **edges out the base rate on ROC-AUC and Brier, not PR-AUC; base-rate priors remain the production backbone**. Current protocol features introduce look-ahead and survivorship limitations. Scores are reported in `artifacts/metrics.json` and the dashboard.

<!-- BEGIN COMPUTED REPORTS -->
## Track record

Excluding Stream: **2/6 advance catches**, **4 misses**
(including 3 same-bar signals), **6h median lead** among catches,
and **$94,535 saved versus a naive 5% price-watcher** on $1M per pair.
Savings include every pair, including late exits. If no EXIT fires, the held position is valued
at its observed worst-14d mark, an unrealized valuation. Both exit strategies assume 1% cost on sale proceeds.

Including the Stream development pairs: **4/8 catches**,
**36h median lead**, **$1,878,696 saved vs naive**.
Controls exclude Stream (no comparable 2024 data): **2.285 false alarms per pair-year**,
from **4 alarms over 1.750 observed pair-years**.
The descriptive stablecoin/CRV breakdown was added after observing controls:
0.000 vs
33.953 alarms per pair-year.
Missing intervals and incomplete 7-day-reference/14-day-follow-up windows are excluded, not treated as calm.

**Limits:** six non-development pairs share **2 distinct crises**;
selection was retrospective for data availability and visible breaks, not prospective holdout validation.
All exposure shares are estimated; CRV is a volatile stress proxy, not the exploited pool itself.
Prices use **4h buckets**, as-of alignment and bounded forward-fill; lead times and assumed exit
prices are uncertain within that sampling interval. The model's risk priors are current, not
historical point-in-time estimates. **Stream is the development case**; no ML early-warning
benchmark is claimed (`rule_vs_ml: null`). Parameters, every pair and sources:
[`artifacts/backtest_results.json`](artifacts/backtest_results.json).

## Market scan

**$435,998,291 gross TVL + AMM liquidity** across **37 positions**:
12 listed Ethereum Morpho V1 vaults ≥ $10M and
25 active Pendle markets ≥ $1M liquidity. Cached universe:
45 listed vaults and 47 active markets;
all qualifying positions analysed, 0 failures.

Largest shared issuer dependency: **Lido — $51,532,121 transmission-weighted
notional across 8 positions**. Top-three issuer concentration index:
**29.1%**, using a capped sum of dominant-path transmissions
per position. Whole-position mapping coverage is **52.5%** to declared
issuer/base-asset depth; **47.5% opaque** (21/37
positions have no unmapped discovered token).

**Limits:** Ethereum only, listed V1 vaults/active markets only, thresholded cached snapshots.
Gross TVL plus pool liquidity can count the same economic capital twice. Transmission-weighted
notionals are model exposures, not unique dollars at risk; dependency columns are not additive.
Manual mappings do not establish complete reserves, validator operators, off-chain counterparties
or tranche waterfalls. Morpho discovery follows funded collateral, excluding loan-asset issuer
risk and idle/dust allocations. Scan ranking is EL minus carry; Pendle scan exit costs are assumed,
not executable quotes for entire pools. Source-cache dates, coverage and full results:
[`artifacts/market_scan.json`](artifacts/market_scan.json).

<!-- END COMPUTED REPORTS -->

### How to run (for judges)
```
python -m venv .venv && .venv/Scripts/pip install -e .
./run.ps1          # or ./run.sh — launches the dashboard from cached data (works offline)
```
Everything is cached to `data/raw/`, so the demo is reproducible offline. See `DEMO.md` for the 2-minute walkthrough.

### Tech
Python · Streamlit · NetworkX · Plotly · scikit-learn · NumPy/SciPy. Free APIs: DefiLlama, Pendle v2, Morpho Blue GraphQL. No API keys, CPU-only.

### Repo
https://github.com/adamew1/blast-radius

### Judging fit
Dependency discovery (recursive, on real data), impact estimation (Monte-Carlo propagation with CVaR + attribution), decision usefulness (STAY/REDUCE/EXIT with the dominant path and real exit cost), working demo on real data (Stream replay + live positions, offline-reproducible).
