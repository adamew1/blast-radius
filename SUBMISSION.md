# DoraHacks BUIDL — ready-to-paste

**Event:** BSA EPFL · The Hackathon — **Belem Capital track** (DeFi Risk Dependency Challenge)
**Submit at:** https://dorahacks.io/hackathon/bsa-the-hackathon/build
**Hard requirement:** a public Git repo link (fill in after pushing). Demo video is recommended, not required.

---

### Project name
Blast Radius

### Tagline (one line)
Find the hidden dependencies behind a DeFi position, simulate how a failure spreads through the stack, and get a defensible STAY / REDUCE / EXIT call — proven on the real Stream Finance collapse of Nov 2025.

### Description (paste into the BUIDL body)
On-chain positions carry risk that lives in their **dependencies** — the settlement chain, the underlying yield source and its issuer, the oracle, the AMM that prices and exits it, and the lending markets that hold it as collateral. When one of these fails, a portfolio manager doesn't just need an alert; they need to know **how the failure propagates to their position** and whether the expected loss justifies exiting despite slippage.

**Blast Radius** is a working Python engine + Streamlit dashboard that does exactly this:

1. **Recursive dependency discovery** — a position (Pendle PT, Morpho vault, or token) is unwrapped layer by layer from live DefiLlama / Pendle / Morpho data. The classic 5-layer Pendle example falls out of generic recursion; it is not hard-coded. Facts the APIs don't expose (issuers, some oracles, backing) come from a small manual map with a source link per entry, labelled in the UI.
2. **Monte-Carlo failure propagation** — each dependency gets an incident probability (base rates from DefiLlama's real `/hacks` dataset) and a loss severity; shocks propagate up the dependency graph (with an explicit oracle→LLTV liquidation rule) to give the position's loss distribution, Expected Loss, CVaR-95, and the dominant risk path.
3. **A real stay/exit decision** — expected loss over the horizon is compared against the real cost of exiting (Pendle price-impact quotes / Morpho withdrawable liquidity) to return STAY / REDUCE / EXIT with a plain-English reason.

**Portfolio mode** finds dependencies shared across a book of 10 positions ("5 of 10 depend on Lido"), shows a position×dependency exposure heatmap, and ranks actions.

**The hero demo** replays the real **Stream Finance → Elixir deUSD** contagion of November 2025 on real DefiLlama prices: Blast Radius discovers that ~65% of deUSD's backing was a loan to Stream, watches the upstream xUSD, and flips to EXIT on **Nov 4** — while sdeUSD was still at $1.07 — three days before it collapsed to ~$0.01. Exiting on that signal avoids a **99.7% loss**, computed from real prices.

We report our models **honestly**: an incident-probability ML model is trained and evaluated against a category base-rate baseline, and because it does not beat the base rate under severe class imbalance, base-rate priors remain the production backbone. Assumptions and limitations are stated openly in the README and the UI.

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
