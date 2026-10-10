# 💥 Blast Radius

**Recursive DeFi dependency discovery, failure propagation, and stay/exit decisions.**

Built for the BSA EPFL × Belem Capital *DeFi Risk Dependency Challenge*. For an on-chain
position, Blast Radius discovers its hidden dependencies, simulates how a failure in any one of
them propagates up to your position, and returns a defensible **STAY / REDUCE / EXIT** call —
proven on the real **Stream Finance** collapse of November 2025.

> Full methodology, model evaluation metrics, assumptions, data sources, and limitations are
> written in Phase 7. This is a work-in-progress scaffold.

## Quick start
```bash
python -m venv .venv
.venv/Scripts/pip install -e .      # Windows (use .venv/bin on macOS/Linux)
python refresh_cache.py             # build the offline cache (one network run)
./run.ps1                           # launch the dashboard (run.sh on macOS/Linux)
```

## Data sources (all free, no API key)
- **DefiLlama** — protocol catalog, TVL history, the `/hacks` incident dataset, historical prices.
- **Pendle** — PT/SY/underlying mapping, market liquidity, expiry, and real exit price-impact quotes.
- **Morpho Blue** — vault allocations, markets, collateral, LLTV, oracle, utilization (current + historical).

Every API response is cached to `data/raw/` so the demo is offline and reproducible. Facts the
APIs do not expose (some oracles, off-chain issuers) live in `data/manual/dependencies.yaml` with a
source link each, and are labelled **manual** in the UI.
