# Blast Radius: Snapshot-only release report

**Verdict: PASS WITH LIMITATIONS.** Validated on 11 October 2026.

The application now uses frozen Snapshot evidence only. The Live page, mode
selector, fetch/replay controls and Live-specific terminal branches are removed.
The five-stage workflow, original $10M portfolio, editable 14-instrument catalog,
locks, constrained optimization, evidence and receipts are preserved. Financial
source files and the native adapter are unchanged, retaining historical receipt
compatibility. Historical API research and replay tools are not an app mode.

## A. Newly executed validation

- **85 tests executed, 85 passed, zero failures:** `python -m unittest discover -s tests`.
- The preceding 95-test suite included 13 tests for the removed Live UI. Those
  obsolete cases were retired; three Snapshot UI tests were added. All 82 other
  financial, API-boundary and historical receipt regressions are retained.
- `scripts/audit_judge_readiness.py`: separate Decimal reconstruction, 80 original
  exact quotes and 4,084,101 combinations; baseline and locked minimum verified.
- `scripts/audit_portfolio_challenge.py`: resized, removed and quote-bounded
  decisions independently enumerated.
- `scripts/audit_catalog.py`: four additional instruments, 40 captured quotes and
  the three alternative portfolio scenarios independently verified.
- All **24 packaged decision/API receipts** passed `scripts/verify_receipt.py`.
- A clean archive of the staged Git tree launched Snapshot and reproduced the
  original rescue with all HTTP requests forbidden.
- Credential-signature and tracked credential-file scans found no credentials.
  These scans are checks for common signatures, not a guarantee about all history.

Machine-readable results: [snapshot validation](artifacts/snapshot_release_validation.json).

## B. Newly executed Playwright rehearsals

| Script | Result and coverage |
|---|---|
| `verify_fire_drill.py` | PASS: clean launch, discovery, graph selection, collapse, rescue, probability comparison, before/after, changed mandate/locks, infeasibility, evidence, receipt download/replay, zero shock, reset, native controls and six research pages |
| `verify_catalog.py` | PASS: add/remove instruments, entirely new $2.25M book, wstETH/apyUSD/USD3 losses and rescue, exact downloaded receipts, removed dependency, reset, native catalog editing |
| `verify_portfolio_challenge.py` | PASS: allocation changes, singleton book, zero shock, quote-limited infeasibility, empty draft preserving the valid decision, reset, native allocation editing |
| `verify_frozen_portfolio.py` | PASS: no Live controls, user's exact five-position $1M book, five stages, downloaded receipt and independent verification |

All four reported **zero JavaScript errors and zero external browser requests**.
The first challenge rehearsal sent a slider edit before the preceding selection
was acknowledged. The harness now waits for the existing busy indicator to clear
and avoids duplicate synthetic change events; the complete rerun passed. The
financial model and user interaction rules were not changed to force a pass.

Detailed evidence: [main browser report](artifacts/fire_drill_verification.json),
[catalog](artifacts/catalog_browser_verification.json),
[challenge](artifacts/challenge_browser_verification.json),
[user portfolio](artifacts/frozen_portfolio_browser_verification.json).
Current screenshots are under `artifacts/screenshots/`.

## C. Financial consistency

Original $10M book, hypothetical 100% wstETH shock and $500k mandate:

| Quantity | USD |
|---|---:|
| Original conditional loss | 2,361,622.14 |
| Residual conditional loss | 481,047.34 |
| Execution/gas reserve | 15,252.51 |
| Conversion reserve | 2,700.00 |
| Accounted loss | 498,999.85 |
| Foregone 30-day carry | 4,417.54 |
| Economic protection cost | 22,370.05 |
| Net released capital | 2,682,047.49 |

Reductions remain **70% PT-wstETH, 100% Steakhouse ETH and 100% Steakhouse USDT**.
Whole-plan break-even scenario probability remains approximately **1.19%**.
Locking PT-wstETH proves the target infeasible; minimum accounted loss **$1,004,800**.

The $2.25M book (PT-apyUSD $500k, PT-USD3 $750k, Vault Bridge WETH/USDC $500k each),
with a $200k mandate, retains these independently audited outcomes:

| Shock | Conditional loss | Accounted loss | Economic cost |
|---|---:|---:|---:|
| wstETH | $309,689.64 | $189,051.21 | $456.53 |
| apyUSD | $500,000.00 | $150,501.13 | $5,124.95 |
| USD3 | $750,000.00 | $151,799.56 | $9,221.25 |

The user's five-position book also passed: Steakhouse ETH $100k, Gauntlet USDC
Prime $150k, Hakutora USDC $150k, Yearn OG USDC $100k and PT-apyUSD $500k.

## D. Demonstration and recovery

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/python.exe -m streamlit run app/Home.py --browser.gatherUsageStats false
```

Open **http://localhost:8501**. The Snapshot terminal opens directly; there is no
mode to select. **Find My Weakest Point ? Simulate Failure ? Build Rescue Plan ?
Show Me the Evidence ? Download decision receipt**. For a custom book, open
**CHALLENGE THIS PORTFOLIO**, add/remove positions, edit allocations and apply.
**Reset** restores the original $10M example. Detailed clicks: [judge guide](JUDGE_GUIDE.md).

Disconnected internet does not affect the demo. For a component problem use
`http://localhost:8501/?fallback=1`. For stale browser state, reload or open a new
private window. Stop/restart Streamlit if necessary; no data refresh is needed.
The backup MP4 preserves the same financial demonstration but predates removal
of the mode selector. Use the application and current screenshots for final UI.

## E. Limits and remaining team actions

1. Frozen observations are historical, not current market conditions or execution
   guarantees. No wallet, withdrawal, swap or cash-conversion transaction is executed.
2. The catalog admits 14 Ethereum instruments, at most ten selected holdings,
   $50k allocation steps and $2M per holding. Exact captured PT quotes cover
   $50k?$1M trade amounts; unsupported sizes cannot be extrapolated.
3. Manual mappings, aggregate collateral recovery, transmission, gas, cash conversion
   and carry remain disclosed assumptions. Model coverage is incomplete.
4. Official event deadlines, eligibility and DoraHacks fields remain team checks.
   No DoraHacks submission is performed. This release is prepared for the user's
   final GitHub-version test and submission.

Submission branch: **main** at `https://github.com/adamew1/blast-radius`.
The three existing feature branches are already merged into main. The final commit
and remote SHA are reported after push; no force push or history rewrite is used.
Frozen evidence, licenses and attribution remain included.
