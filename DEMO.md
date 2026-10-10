# Blast Radius — 2-minute demo script

Launch: `./run.ps1` (Windows) / `./run.sh` → opens the dashboard on cached data (works offline).

**0:00 — The problem (Belem's words).** On the **Home** page: a portfolio manager holds on-chain
positions whose real risk is hidden in their *dependencies* — settlement chain, underlying yield
source & issuer, oracle, AMM liquidity, lending markets. When one fails, flagging the incident
isn't enough; you need to know **how it propagates to your position** and whether the expected
loss justifies exiting despite slippage. Scroll down: the methodology and the **honest** model
evaluation (the model improves ROC-AUC/Brier, not PR-AUC; base-rate priors remain the backbone).

**0:25 — Position (live look-through).** Open **Position → Pendle PT-sUSDS**. The dependency graph
is built live: the **5 layers fall out** — Ethereum chain, the Pendle AMM, sUSDS → USDS → **Sky**
(issuer), the oracle, and the **Morpho lending market that holds the PT as collateral**. Solid =
live API, dashed = sourced manual facts. Verdict: **REDUCE** — carry covers the mean loss but the
CVaR-95 tail is fat. Flip the **what-if** toggle on the Sky issuer → expected loss jumps and the
verdict flips to **EXIT**.

**0:55 — Portfolio (shared dependencies).** Open **Portfolio**. 10 positions, $10M. Headline:
**"5 of 10 positions depend on Lido"** — correlated risk the per-position view hides. The
**heatmap** shows which positions are exposed to which dependency, and the **ranked actions**
table gives an EXIT/REDUCE/STAY call each, worst risk-adjusted first.

**1:25 — Replay: Stream Finance (the development case).** Open **Replay**. You hold \$1M of
Elixir **sdeUSD**. Slide to **Nov 4, 2025**: Stream discloses its \$93M loss, **xUSD breaks to
\$0.95** — but sdeUSD is *still \$1.07*. Blast Radius already says **EXIT**, because it saw the
upstream break and knew deUSD was 65% backed by Stream. Slide to **Nov 7**: sdeUSD collapses to
~\$0.01. **Exiting on the Nov-4 signal avoids a 99.7% loss — 3 days before the asset visibly
broke.** This is a gross daily-price comparison before exit costs, built knowing the outcome.

**1:55 — Track Record / Market Scan.** Show the primary numbers excluding Stream, misses and
overall false alarms, then the Ethereum scan and opaque share. Use `artifacts/pitch.txt` for
current numbers and caveats. Do not call six pairs six independent crises.
