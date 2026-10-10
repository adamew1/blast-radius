# Blast Radius — two-minute live story

Launch `./run.ps1` or `.venv/Scripts/python.exe -m streamlit run app/Home.py`. Open the displayed local URL at 1500×1100 or larger. The presentation forces offline mode. Start with **Reset**. The native-control fallback is `/?fallback=1`.

## 0:00–0:15 · The illusion

“Ten investments. Ten million dollars. You think you're diversified. But you might have bought the same risk five times.”

Show the ten investment cards. Click **FIND MY WEAKEST POINT**.

## 0:15–0:35 · The discovery

“The graph found wstETH underneath a Pendle position and four Morpho vaults. Different products. A common underlying bet. This ranking is computed from the graph; Lido is the linked issuer scenario.”

Point to the five connections. Highest conditional damage, gross affected capital, and position count are calculated from the frozen book. A total wstETH intrinsic-loss shock is the standardized ranking scenario, not a forecast.

## 0:35–1:00 · The catastrophe

Click **SIMULATE FAILURE**.

“Follow the real dependency paths. Under this hypothetical total-loss shock, the modelled portfolio loss is $2.31 million. Wrapper paths overlap; separate funded lending allocations add. Supplier losses depend on collateral shortfall, not simply the liquidation threshold.”

Animation conveys causal propagation, not real incident time. Avoid changing severity during the core pitch unless asked; the control remains available.

## 1:00–1:25 · The rescue

Keep the **$500,000** loss limit. Click **BUILD RESCUE PLAN**. Show the transformed exposures and scroll to the comparison.

“Before that failure, how cheaply can we protect this book? The optimizer chooses reductions within captured quote and shared market-liquidity bounds. It gets accounted loss below $500,000 for roughly $21,800 in execution, conversion reserve and foregone yield. Six investments remain untouched.”

Point to the three comparable strategies. The displayed maximum includes residual loss, execution costs and conversion reserve. Foregone carry belongs to the economic objective and is shown separately.

## 1:25–1:45 · The challenge

Check **PT-wstETH** under position locks and click **BUILD RESCUE PLAN** again.

“Tell it this position cannot be sold. Now that target is infeasible. The system shows what can actually be attained; it doesn't manufacture a rescue.”

The infeasible result is real. It is not a scripted outcome or an executed trade.

## 1:45–2:00 · The proof

Click **Show Me the Evidence**.

“Inspect the source, the assumptions and every candidate exit. We even verified token decimals on chain: PT-reUSD has six, not eighteen. The protection's break-even scenario probability is visible, so conditional damage isn't confused with expected loss.”

“In DeFi, your biggest risk isn't always the position you own. It's the dependency you didn't know you owned. Blast Radius discovers it, measures the damage, and finds the cheapest feasible protection under real liquidity constraints.”

## Skeptical-judge answers

- **Are you predicting a Lido failure?** No. The screen calculates losses conditional on a chosen hypothetical shock. A separate preserved model evaluates expected loss using priors.
- **Is this a trading recommendation?** It minimizes the economic cost of meeting a scenario limit. The break-even probability says when protection would justify its cost under this model; any supplied scenario probability is an assumption.
- **Are the quotes live?** No. They are genuine cached quotes with asset marks, timestamps and RPC-verified decimals. Failed quote options are unavailable. No transactions are sent.
- **Can these withdrawals execute?** The plan respects snapshot allocation and shared-market liquidity bounds. Withdrawal queues, future liquidity and actual transaction execution are not certified.
- **What is incomplete?** The book contains unresolved collateral; loan-asset issuer risk and full reserve look-through are incomplete. Aggregate recovery and transmission coefficients are explicit assumptions.

## Reproduce and recover

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe scripts/build_fire_drill_artifacts.py
.venv/Scripts/python.exe scripts/verify_receipt.py
.venv/Scripts/python.exe scripts/verify_fire_drill.py --record
```

Current numbers: `artifacts/fire_drill.json` and `artifacts/fire_drill_pitch.txt`.
Fallback screenshots: `artifacts/screenshots/FireDrill_*.png`.
Browser recording and verification paths: `artifacts/fire_drill_verification.json`.
If component interaction fails, open `/?fallback=1`; it uses native controls and the same financial engine.
