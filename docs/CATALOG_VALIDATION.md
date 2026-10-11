# Constructing portfolios beyond the original ten

Challenge Mode now admits **14 genuine Ethereum instruments**, with dynamic add/remove controls and a maximum of ten selected positions. A judge can construct a portfolio using only newly admitted instruments and run Discover → Attack → Collapse → Rescue → Prove. This extends the earlier allocation-only mode; it does not provide arbitrary address, wallet, chain or protocol support.

## Newly admitted instruments

| Instrument | Observed contract/market | Own execution and financial evidence |
|---|---|---|
| Pendle PT-apyUSD · 2026-11-05 | `0xc5f938a8ef5f3bf9e72f5aa094baf5e03f4727d3` | Twenty exact $50k–$1M exit quotes, own PT/output marks, RPC decimals and market APY |
| Pendle PT-USD3 · 2026-12-17 | `0x4a5067c3ff1abb7449244025b0e37feaf77d8e3e` | Twenty separate exact $50k–$1M exit quotes, own PT/output marks, RPC decimals and market APY |
| Morpho Vault Bridge WETH | `0x31A5684983EeE865d943A696AAC155363bA024f9` | Its own vault response: allocations, supply/debt/collateral, market liquidity and net APY |
| Morpho Vault Bridge USDC | `0xBEefb9f61CC44895d8AEc381373555a64191A9c4` | Its own vault response: allocations, supply/debt/collateral, market liquidity and net APY |

Descriptions and admission data are in [catalog.json](../data/fire_drill/catalog.json). The additional quote bundle is [catalog_execution.json](../data/fire_drill/catalog_execution.json). The original book and original execution bundle were preserved; additional captures use separate files. The capture script refuses to overwrite an existing catalog.

**Excluded:** Steakhouse USDC (`0xBEEF01735c132Ada46AA9aA4c54623cAA92A64CB`). Its material funded steakEURCV market reports no `collateralAssetsUsd`. The unchanged stress engine rejects that incomplete balance sheet. No collateral value was invented, borrowed, or silently treated as zero. The exclusion is recorded in the catalog and independent audit.

## Correctness of the constructed book

1. **Selection:** server validation permits only catalog IDs and canonical instrument identities. Duplicate instrument rows, arbitrary addresses and more than ten positive allocations are rejected. Zero or Remove excludes the instrument; an empty book is rejected.
2. **Discovery:** each admitted position runs through the existing recursive Pendle/Morpho resolvers. Pendle uses its own market/PT/underlying relationships; Morpho follows that vault's funded collateral allocations and observed market oracle addresses. Existing sourced manual mappings remain explicitly manual. Unknown backing remains unknown.
3. **Stress:** the original deterministic model is unchanged. PT underlying shocks transmit one-for-one at a fixed discount factor. Vault losses use each vault's own funded weights and each market's incremental collateral shortfall divided by supply. Nothing copies another instrument's APY, collateral composition or loss fraction.
4. **Execution:** PT candidates retain exact captured dollar trade amounts, original quoted outputs and mark shortfalls. Resizing changes only the exit fraction and the quantity-dependent assumed reserves/carry. Missing quotes stay unavailable; holdings above $1M cannot extrapolate into larger trades. Morpho candidate funding is bounded by its own observed claims and shared market capacity, counted once. Across differently timed captures, the shared capacity is the minimum observed bound.
5. **Optimization:** the unchanged MILP receives the newly discovered/stressed book and its candidates/resources. It selects reductions under the requested accounted-loss limit, locks and shared constraints. Per-position APY supplies foregone carry. Feasibility is checked again in dollar units.
6. **Evidence/state:** version 3 receipts embed the constructed book and the relevant frozen execution bundle, supporting reconstruction against the admitted catalog. Versions 1 and 2 remain supported for earlier original-universe receipts. Membership changes clear prior plans and remove invalid dependencies/locks. Reset restores the original $10M demonstration.

## Frozen evidence and remaining limits

New admitted instrument evidence was retrieved **2026-10-11 02:24:45–02:29:01 UTC**. New token decimal calls use Ethereum block **`0x18f43b9`**, whose header timestamp is recorded and checked independently. Existing Pendle market listings/APYs and manual mappings retain their original capture/version dates. Asset marks also retain their own provider update times. These are composite captures, **not an atomic snapshot or current executable order book**. Every receipt hashes the source files; hashing establishes reproducibility, not provider authentication.

PT quotes return their underlying tokens, not external cash. The cash conversion reserve (10 bps) and gas reserve (2 bps) remain assumptions. There is no second-leg cash quote, certified withdrawal queue or transaction execution. No transaction was submitted. Unknown backing, loan-asset issuer risk, borrower-level liquidation dynamics, dust/idle omission and other existing model boundaries still apply. Admission means the existing declared model can be calculated from recorded inputs; it does not certify the instrument's safety or complete risk coverage.

## Independent validation

The independent [catalog audit](../scripts/audit_catalog.py) imports neither the financial engine nor SciPy. It verifies original request/cache identities, RPC decimal responses and block header, each instrument's asset marks, exact integer input quantities and raw outputs for all **40 new quotes**, and funded lending balance sheets. A separate Decimal implementation recomputes losses, costs and withdrawal funding, then exhaustively enumerates the affected candidates. Each selected feasible plan attains the independently calculated relaxed lower bound, proving the stated discrete optimum with actual capacities included.

The audited book is entirely new: PT-apyUSD **$500k**, PT-USD3 **$750k**, Vault Bridge WETH **$500k**, Vault Bridge USDC **$500k**; total **$2.25M**. All scenarios below use a 100% intrinsic token shock and a **$200k accounted-loss limit**.

| Shock | Conditional loss | Accounted loss after rescue | Economic protection cost | Independently enumerated combinations |
|---|---:|---:|---:|---:|
| wstETH | $309,689.64 | $189,051.21 | $456.53 | 441 |
| apyUSD | $500,000.00 | $150,501.13 | $5,124.95 | 11 |
| USD3 | $750,000.00 | $151,799.56 | $9,221.25 | 16 |

These are conditional model results, not observed failure outcomes. The discrete quote grid explains why a least-cost rescue can finish appreciably below the limit.

Catalog admission originally passed 47 tests; the final release suite passes **75 tests**, including 28 Live Mode regressions. Browser rehearsals block external requests and cover the original demo, allocation-only challenges and a catalog book assembled through actual Add/Remove controls. The catalog rehearsal checks three shocks, their optimized/downloaded receipts, removing a newly added dependency, Reset to the original rescue and adding a new PT through the native fallback.

Evidence: [independent audit](../artifacts/catalog_independent_audit.json), [catalog browser rehearsal](../artifacts/catalog_browser_verification.json), [original browser rehearsal](../artifacts/fire_drill_verification.json), [allocation challenge rehearsal](../artifacts/challenge_browser_verification.json).

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe scripts/build_fire_drill_artifacts.py
.venv/Scripts/python.exe scripts/audit_judge_readiness.py
.venv/Scripts/python.exe scripts/verify_receipt.py
.venv/Scripts/python.exe scripts/build_challenge_artifacts.py
.venv/Scripts/python.exe scripts/audit_portfolio_challenge.py
.venv/Scripts/python.exe scripts/build_catalog_artifacts.py
.venv/Scripts/python.exe scripts/audit_catalog.py
# With the local application running:
.venv/Scripts/python.exe scripts/verify_fire_drill.py
.venv/Scripts/python.exe scripts/verify_portfolio_challenge.py
.venv/Scripts/python.exe scripts/verify_catalog.py
```

## Judge follow-up

After the original pitch, open **Challenge this portfolio**, remove its rows, and add the four new instruments above. Apply, discover, then select wstETH and use the $200k limit. The graph finds shared collateral in the newly chosen vaults and prices a new rescue. Select apyUSD or USD3 to demonstrate each new PT's different economics and own quotes. Download the receipt and Reset to return to the original demonstration.
