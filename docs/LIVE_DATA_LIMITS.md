# Live data feasibility review

Reviewed before implementation, 2026-10-11. The final universe contains six
Ethereum Pendle PT markets and eight Morpho vaults. Allocations remain illustrative
USD amounts, not wallet balances. No arbitrary address import is supported.

## Inputs and refresh boundaries

| Input | Refreshable observation | Remaining boundary |
|---|---|---|
| Morpho vault | Funded allocations, total assets, net APY, state timestamp/block | Vault V1 schema only; no V2 adapter discovery |
| Morpho market | Collateral identity/value, debt, supply, liquidity, APYs, oracle address, timestamp/block | Aggregate balance sheet; no borrower liquidation simulation |
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

The existing `/swap` schema is still used for exact-size quotes; it was the
repository's captured/validated response contract. If the provider removes it or
returns an unrecognized schema, the run remains risk-only. The implementation does
not guess how to value a different Convert response. No transaction is submitted.

Primary references checked:

- https://docs.morpho.org/developers/api/get-started/ (schema evolution, limits, no SLA)
- https://docs.pendle.finance/pendle-v2-dev/Backend/ApiOverview (CU limits, pagination)
- https://docs.pendle.finance/pendle-v2/Developers/Backend/HostedSdk (Convert migration)
