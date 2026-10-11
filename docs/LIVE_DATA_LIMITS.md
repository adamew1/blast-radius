# Archived Live data feasibility review

The Live application page was removed at the user's request. The current product
is Snapshot-only. This document records historical research and limitations; its
Live UI instructions do not describe the current application.

Reviewed before implementation, 2026-10-11. The final universe contains six
Ethereum Pendle PT markets and eight Morpho vaults. Allocations remain illustrative
USD amounts, not wallet balances. No arbitrary address import is supported.

## Inputs and refresh boundaries

| Input | Refreshable observation | Remaining boundary |
|---|---|---|
| Morpho vault | Native funded allocations and total assets, net APY, state timestamp/block, timestamped asset price | Vault V1 schema only; no V2 adapter discovery |
| Morpho market | Native collateral, debt, supply and liquidity, token decimals and timestamped prices, APYs, oracle address, timestamp/block | Aggregate balance sheet; no borrower liquidation simulation |
| Pendle market | Active membership, PT/SY/underlying identity, pool liquidity, APY, expiry, data timestamp | Active universe only; expired/unlisted holdings must be rejected |
| Pendle assets | USD marks, provider price times, decimals | Marks can lag a newly retrieved response |
| Token decimals | Fresh RPC eth_call at a timestamped block | RPC/API mismatch must reject the quote |
| Pendle exit | SDK quote for one exact integer token amount | No interpolation, scaling, split-trade composition or guaranteed fill |
| Dependency semantics | API collateral/PT identities | Wrapper backing, issuer, token-level oracle names and backing shares remain a versioned manual map |
| Portfolio | User-entered supported allocations | Not an observed wallet; refreshed marks do not change hypothetical USD allocations |
| Financial model | Existing stress and constrained optimizer | Transmission, fixed PT discount, gas (2 bps), conversion (10 bps), 30-day carry, residual proportions remain assumptions |

The old HTTP cache returns any existing response indefinitely, even online; merely
turning off OFFLINE is insufficient. Live requests must bypass that cache entirely
and must never overwrite the validated snapshot files. Discovery's old top-50 vault
scan is neither comprehensive nor timestamp-checked. Live discovery will explicitly
bound lending-contagion evidence to the eight admitted vaults, and disclose that scope.

Live schema probes confirmed Morpho `VaultState.timestamp/blockNumber` and
`MarketState.timestamp/blockNumber/supplyApy/borrowApy`. Pendle `/markets/active`
has a market creation timestamp, which is NOT a freshness timestamp. Its per-market
`/data.timestamp` and asset `priceUpdatedAt` are checked separately.

## Gaps preventing an executable end-to-end rescue

1. PT exits return an underlying token, often the dependency being attacked. The
   assumed 10 bps conversion reserve is not a freshly quoted cash leg.
2. Morpho funded claims and shared liquidity are necessary bounds, not certified
   withdrawable amounts. Withdrawal queues, pauses, permissions, slippage and a
   user's executable withdrawal transaction are not captured.
3. APIs are indexed, asynchronous and rate limited. Retrieval time cannot replace
   missing provider times, nor certify an atomic block. Pendle's documented SDK
   evolution and computing-unit limits can make a quote grid unavailable or expire
   while it is captured. Reject 429/timeouts; allow fewer observed candidates, never
   infer the missing sizes. The existing observed swap response schema remains
   supported; a removed endpoint fails closed rather than guessing a Convert schema.
4. Manual mappings have version hashes, not live reserve attestations. Unmapped
   collateral means incomplete dependency coverage and prohibits a rescue claim.

Consequently fresh, complete risk data enables conditional risk analysis. Fresh
quote evidence additionally enables the unchanged optimizer to calculate an
**indicative model rescue**, explicitly never an executable trade plan. Missing or
stale execution evidence leaves risk-only analysis. Missing/stale material risk
inputs reject analysis. Snapshot Mode remains a separate, explicit offline fallback.

## Implemented checks and observed availability

Vault allocation claims must reconcile to total assets within max($0.02, 1 ppm).
Unreported idle assets need separate evidence and are rejected rather than assumed
safe. A funded loan-only idle market with no debt has no collateral valuation to
fetch; it is explicitly allowed without manufacturing a collateral mark. Funded
collateral markets require collateral value, debt, supply and liquidity. Lending
liquidity must reconcile to supply minus debt within the same tolerance.

Because independently indexed nested market states differed during a live probe,
the implementation now fetches dedicated `marketById` observations in batches of
twenty. Each shared market uses one fresh state, while identities/LLTV must agree
with vault observations. All original responses remain embedded in the receipt.
This is consistent reuse of an asynchronous observation, not atomicity.

Morpho-only portfolios fetch the selected vaults, not every unrelated catalog
vault. Direct PT positions retain the eight-vault contagion scan. The exact scope
is embedded in every new live receipt. Vault requests also include raw total and
allocation asset amounts, making unit reconciliation evidence inspectable alongside
USD valuations. All freshness and reconciliation thresholds remain unchanged.

A real probe at approximately 2026-10-11 03:16 UTC was rejected because the
Steakhouse ETH vault state was about 46 minutes old, exceeding the 15-minute risk
policy. The rejected capture's receipt replayed offline successfully. This is an
observed availability limit, not grounds to relax freshness or load old balances.
Mocked fresh responses exercise the complete workflow independently of API uptime.

### Stale-market rejection and recovery (2026-10-11)

A user capture at **04:38:07 UTC** rejected Smokehouse USDT's
**PT-sUSDS-26NOV2026 / USDT** market
`0x0367161b7cb23dfd03747dd3815d1c445b0437b648a6d50346249c6e7b92ff1b`.
Its provider timestamp was **04:04:59 UTC**, age **1,988.8 seconds**, exceeding the
unchanged **900-second** risk limit. Direct requests to both Morpho GraphQL hostnames
still returned that timestamp around **04:41 UTC**. Refreshing the browser or
replacing the timestamp with HTTP retrieval time cannot make this input fresh.

The original UI showed a contract hash and a timestamp window containing only the
first accepted vault observation. This hid the failed market's older timestamp.
The UI now identifies the holding and market, shows the rejected provider time
and age, and labels the accepted time window as partial. **Load $1M Hakutora live
example** explicitly replaces the Live selection and clears previous results;
the user must then fetch new observations. No automatic portfolio substitution,
historical fallback, financial model change or freshness relaxation is used.

A separate real HTTP Hakutora/cbBTC run at **04:42:08 UTC** passed with vault and
market timestamps **04:35:47 / 04:39:11 UTC** (ages 382 / 178 seconds). Its $1M
illustrative holding produced **$901,379.25** conditional loss and **$496,298.59**
accounted loss with a **45% indicative reduction**. The receipt replay passed.
Runtime evidence: `artifacts/live/fd111bdcf355a2c18911de0cb40e28108904c947a9055a1211a127f56171304a.json`.
These historical checks do not guarantee the next request will pass. Gas, cash
conversion and manual dependency mappings remain assumed; execution is uncertified.

A browser request at **04:46:05 UTC** was rejected for inconsistent Morpho dollar
valuations: allocation sum $15,315,705.93 versus vault total $15,316,132.55. The
reconciliation threshold was preserved. A separate explicit request at
**04:47:15 UTC** passed freshness and reconciliation, with vault/market timestamps
**04:45:47 / 04:39:11 UTC** (ages 88 / 484 seconds), and the same rounded financial
results as the earlier run. Download/replay and independent Decimal enumeration
of all 21 candidates passed. This receipt is packaged at
`artifacts/certified_live/hakutora_recovery_20261011_receipt.json`.
The real browser also verified clear stale-market messaging, explicit portfolio
replacement without an automatic fetch, and Snapshot baseline recovery, with no
JavaScript errors. The complete automated suite passed **78/78 tests**, including
three new UI recovery regressions. Historical release reports describe the earlier
75-test release.

The existing `/swap` schema is still used for exact-size quotes; it was the
repository's captured/validated response contract. If the provider removes it or
returns an unrecognized schema, the run remains risk-only. The implementation does
not guess how to value a different Convert response. No transaction is submitted.

## User-requested delayed-data window

After the 04:47 recovery, the user explicitly requested a higher maximum age.
The Live interface now defaults to a **60-minute risk age and timestamp-spread
window**, with a **15-minute strict** option. The command-line and financial
client defaults remain 15 minutes; previously certified receipts and their model
hashes remain unchanged. The Hakutora example resets the interface to strict mode.

Accepted data outside the strict 15-minute standard is labelled **delayed risk
observations**, never verified fresh live data. Any rescue remains indicative and
is labelled as using delayed data. New UI receipts include the selected policy,
actual maximum age/spread, and `strict_15_minute_risk_passed`; their top-level
classification distinguishes delayed, rejected and fresh observations. Policy
changes require a new capture and clear any previous recommendation. The exact
responses and provider timestamps remain embedded; historical data is not loaded.

The two-minute mark/quote/RPC limits, future tolerance, balance reconciliation,
shared liquidity rules and optimizer mathematics are unchanged. A real full-book
probe at **04:54:13 UTC** passed the previously failing market's age check under
60 minutes, then correctly rejected inconsistent lending-market balances. Raising
the age limit does not resolve independent provider inconsistencies or certify
full-book live coverage.

Validation after this policy change: **81/81 automated tests passed**, including
delayed-data labelling, receipt replay/classification tampering, policy-change
invalidation, over-age/future rejection and unchanged quote expiry. All six
packaged live success/rejection receipts replayed. A real browser capture at
**05:00:57 UTC** used the 60-minute policy, passed the earlier age check, and
retained the independent balance rejection. Its receipt replayed; the browser
also verified strict-example reset and unchanged Snapshot rescue recovery with
no JavaScript errors. This was a safely rejected request, not a newly certified
full-book live analysis.

Primary references checked:

- https://docs.morpho.org/developers/api/get-started/ (schema evolution, limits, no SLA)
- https://docs.pendle.finance/pendle-v2-dev/Backend/ApiOverview (CU limits, pagination)
- https://docs.pendle.finance/pendle-v2/Developers/Backend/HostedSdk (Convert migration)

## Native-unit correction (2026-10-11, 05:22 UTC)

**Original issue and consequence.** The higher age limit exposed a distinct
valuation problem. At 05:00:57, Smokehouse's PT-sUSDS/USDT market reported supply
$5,155,328.55264408, debt $4,300,831.227781188 and liquidity $854,482.7707639054.
The USD identity missed by $14.5541, beyond the $5.1553 tolerance. Other markets
and a vault total showed similar display-price drift. The correctly conservative
validator rejected these inputs. The failing v1 capture is preserved as
`artifacts/certified_live/usd_display_mismatch_20261011_receipt.json`.

**Fix.** The free Morpho GraphQL API also exposes native balances, token decimals
and `asset.price { usd timestamp }`. The new acquisition adapter computes USD
values from these observations, reusing one observed price per token across
vaults and shared markets. For the same market, native supply 5,159,678,817,474
minus debt 4,304,463,879,720 equals liquidity 855,214,937,754 exactly (six decimals).
Native balance reconciliation allows at most one base unit for market rounding;
vault total versus allocation rounding allows at most one base unit per funded
allocation. A larger native gap, unreported idle funds or missing fields still
rejects. The original USD validator, loss model and optimizer are unchanged.
Yahoo market prices cannot replace protocol allocations, debt or collateral;
no generic market-feed fallback is used. Morpho REST native-state and price
endpoints were also probed; GraphQL already supplies the required fields together.

Risk-token price timestamps are material risk observations, subject to the
selected 15/60-minute age **and spread** policy and checked again at decision
time. They are not execution marks: Pendle execution marks, quotes and RPC retain
their 120-second limits. The new v2 receipt preserves the exact raw responses,
reported display USD values, native balances, selected prices and derivation
ledger, plus a hash of `app/live_data.py`. Replay reruns that adapter and the
unchanged financial engine. Archived v1 and Snapshot source hashes still match.

**Actual validation.** All **89 tests passed**, including eight new native/API/UI
regressions. Separate Decimal calculations check native balances, decimal
scaling, raw source prices and the normalization ledger without importing product
financial code. The baseline and both alternative-portfolio independent audits
passed unchanged. All ten packaged live success/rejection receipts replayed.

The real browser run at **05:22:54 UTC** covered the original ten $1M positions,
eight vaults, 37 markets and 21 risk-token prices, with **16 exact Pendle swap
requests**. The hypothetical 100% wstETH loss was **$2,359,706.70**. Risk provider
timestamps spanned **04:51:02–05:21:35**; oldest risk age was **1,912.33 seconds**,
spread **1,833 seconds**. It passed the selected 3,600-second policy, **failed
strict 900-second certification**, and was labelled delayed risk-only analysis.
Incomplete manual coverage in Steakhouse USDT and Yearn OG USDC prohibited rescue.
No JavaScript errors occurred, receipt download/replay passed, and one-click
Snapshot fallback reproduced the original rescue.

A separate **05:24:19 UTC** Hakutora/cbBTC run under the explicit 60-minute policy
completed the optimizer: loss **$901,368.61**, 45% indicative reduction, accounted
loss **$496,292.74**. Vault timestamp **04:55:35**, market **05:23:59**, USDC/cbBTC
prices **05:18:55**. It passed the selected policy, **not** strict certification;
an independent Decimal reconstruction exhaustively checked all 21 options.
At **05:23:34 UTC**, the strict Hakutora attempt correctly rejected the same
04:55:35 vault state (age 1,679.4 seconds). No stale substitution was performed.

User allocations, dependency mappings, transmission/recovery, unchanged residual
mix, gas and cash conversion remain hypothetical or assumed. Withdrawal
execution and conversion are uncertified; the complete ten-position fresh
end-to-end workflow remains uncertified. See
`artifacts/certified_live/native_normalization_audit.json` and the distinctly named
native delayed/strict-rejected receipts. Historical replay is not fresh analysis.

Native field references: [Morpho markets API](https://docs.morpho.org/developers/api/morpho/)
and [Morpho vaults API](https://docs.morpho.org/developers/api/morpho-vaults/).
