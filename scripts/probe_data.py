"""Phase-1 data probe: does the real data exist to build the backtest + market scan?

For each candidate contagion event, try to pull a DefiLlama price series for BOTH the upstream
asset (the hidden dependency that broke first) and the downstream asset (what a fund held), at the
finest granularity that returns data (1h -> 4h -> 1d) over [event-10d, event+21d]. We record what
exists and whether the known move is visible, then DROP any event missing a usable series for
either leg. We also probe whether Morpho can list all Ethereum vaults and Pendle all active markets.

Run:  .venv/Scripts/python.exe scripts/probe_data.py
Writes artifacts/probe.json and prints a readable table. Live calls populate data/raw/ (cache).
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from blast_radius.sources import defillama, morpho, pendle  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
DAY = 86400


def _epoch(date_str: str) -> int:
    return int(dt.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp())


# period -> (span points to cover ~31 days, seconds per point)
_GRAN = [("1h", 31 * 24, 3600), ("4h", 31 * 6, 4 * 3600), ("1d", 31, DAY)]


def _fetch_leg(keys: list[str], event_date: str) -> dict:
    """Try each coin key x each granularity; keep the finest granularity that returns >=10 points."""
    start = _epoch(event_date) - 10 * DAY
    best = None
    for key in keys:
        for period, span, _sec in _GRAN:
            try:
                raw = defillama.chart(key, start=start, span=span, period=period)
            except Exception as e:  # noqa: BLE001
                best = best or {"key": key, "period": period, "ok": False, "error": repr(e)[:160]}
                continue
            pts = ((raw.get("coins") or {}).get(key) or {}).get("prices", [])
            if len(pts) < 10:
                continue
            prices = [p["price"] for p in pts]
            ts = [p["timestamp"] for p in pts]
            ev = _epoch(event_date)
            # reference = median of points strictly before the event
            pre = sorted(p["price"] for p in pts if p["timestamp"] < ev)
            ref = pre[len(pre) // 2] if pre else prices[0]
            post = [p["price"] for p in pts if p["timestamp"] >= ev]
            lo_post = min(post) if post else min(prices)
            drawdown = (ref - lo_post) / ref if ref else 0.0
            return {
                "key": key, "period": period, "ok": True, "n_points": len(pts),
                "covers_days": round((ts[-1] - ts[0]) / DAY, 1),
                "ref_pre_event": round(ref, 6), "min_after_event": round(lo_post, 6),
                "drawdown_pct": round(100 * drawdown, 2),
                "first_ts": ts[0], "last_ts": ts[-1],
            }
    return best or {"key": keys[0] if keys else None, "ok": False, "error": "no data at any granularity"}


# ---- candidate events (upstream = what broke first; downstream = what a fund held) ----
CANDIDATES = [
    # --- 2023 stablecoin depeg family (SVB / USDC) ---
    dict(name="USDC depeg (SVB) -> DAI", date="2023-03-11", dep_type="backing",
         upstream=["coingecko:usd-coin"], downstream=["coingecko:dai"]),
    dict(name="USDC depeg (SVB) -> FRAX", date="2023-03-11", dep_type="backing",
         upstream=["coingecko:usd-coin"], downstream=["coingecko:frax"]),
    dict(name="USDC depeg (SVB) -> MIM", date="2023-03-11", dep_type="backing",
         upstream=["coingecko:usd-coin"], downstream=["coingecko:magic-internet-money"]),
    dict(name="USDC depeg (SVB) -> alUSD", date="2023-03-11", dep_type="backing",
         upstream=["coingecko:usd-coin"], downstream=["coingecko:alchemix-usd"]),
    dict(name="USDC depeg (SVB) -> USDD", date="2023-03-11", dep_type="backing",
         upstream=["coingecko:usd-coin"], downstream=["coingecko:usdd"]),
    dict(name="USDC depeg (SVB) -> GHO", date="2023-03-11", dep_type="backing",
         upstream=["coingecko:usd-coin"], downstream=["coingecko:gho"]),
    # --- 2023 Euler hack -> agEUR (upstream proxy = EUL / Euler) ---
    dict(name="Euler hack -> agEUR", date="2023-03-13", dep_type="issuer",
         upstream=["coingecko:euler"], downstream=["coingecko:ageur"]),
    # --- 2023 Curve/Vyper reentrancy -> depegged pool tokens (upstream proxy = CRV) ---
    dict(name="Curve/Vyper -> alETH", date="2023-07-30", dep_type="liquidity",
         upstream=["coingecko:curve-dao-token"],
         downstream=["coingecko:alchemix-eth", "ethereum:0x0100546f2cd4c9d97f798ffc9755e47865ff7ee6"]),
    dict(name="Curve/Vyper -> pETH", date="2023-07-30", dep_type="liquidity",
         upstream=["coingecko:curve-dao-token"],
         downstream=["ethereum:0x836a808d4828586a69364065a1e064609f5078c7", "coingecko:jpegd-peth"]),
    dict(name="Curve/Vyper -> msETH", date="2023-07-30", dep_type="liquidity",
         upstream=["coingecko:curve-dao-token"],
         downstream=["ethereum:0x64351fc9810adad17a690e4e1717df5e7e085160", "coingecko:metronome-synth-eth"]),
    # --- 2024 Renzo ezETH depeg (liquidity) ---
    dict(name="Renzo ezETH depeg", date="2024-04-24", dep_type="backing",
         upstream=["coingecko:renzo-restaked-eth", "ethereum:0xbf5495efe5db9ce00f80364c8b423567e58d2110"],
         downstream=["ethereum:0xbf5495efe5db9ce00f80364c8b423567e58d2110"]),
    # --- 2025 Usual USD0++ depeg (upstream) -> USD0 ---
    dict(name="Usual USD0++ depeg", date="2025-01-10", dep_type="backing",
         upstream=["coingecko:usd0-liquid-bond", "coingecko:usual-usd0"],
         downstream=["coingecko:usual-usd0", "coingecko:usd0-liquid-bond"]),
    # --- 2025 Stream Finance -> Elixir deUSD / sdeUSD (DEVELOPMENT CASE, already cached) ---
    dict(name="Stream xUSD -> deUSD", date="2025-11-04", dep_type="backing",
         upstream=["coingecko:staked-stream-usd"], downstream=["coingecko:elixir-deusd"]),
    dict(name="Stream xUSD -> sdeUSD [DEV CASE]", date="2025-11-04", dep_type="backing",
         upstream=["coingecko:staked-stream-usd"],
         downstream=["ethereum:0x5c5b196abe0d54485975d1ec29617d42d9198326"]),
    # --- 2025 Balancer v2 exploit -> contagion candidates (probe which, if any, broke) ---
    dict(name="Balancer v2 exploit -> osETH", date="2025-11-03", dep_type="liquidity",
         upstream=["coingecko:balancer"], downstream=["coingecko:stakewise-v3-oseth"]),
    dict(name="Balancer v2 exploit -> wstETH", date="2025-11-03", dep_type="liquidity",
         upstream=["coingecko:balancer"], downstream=["coingecko:wrapped-steth"]),
]


def probe_events() -> list[dict]:
    out = []
    for ev in CANDIDATES:
        up = _fetch_leg(ev["upstream"], ev["date"])
        dn = _fetch_leg(ev["downstream"], ev["date"])
        usable = bool(up.get("ok") and dn.get("ok"))
        out.append({**ev, "upstream_probe": up, "downstream_probe": dn, "usable": usable})
        flag = "OK " if usable else "DROP"
        print(f"[{flag}] {ev['name']:<34} up={up.get('period') or '-':>2}/{up.get('n_points','-'):>3}pt "
              f"dd={up.get('drawdown_pct','-')}%  dn={dn.get('period') or '-':>2}/{dn.get('n_points','-'):>3}pt "
              f"dd={dn.get('drawdown_pct','-')}%")
    return out


def probe_morpho() -> dict:
    res = {}
    try:
        vaults = morpho.vaults((1,), first=200)
        tvls = sorted((v.get("state") or {}).get("totalAssetsUsd") or 0 for v in vaults)
        res["ethereum"] = {
            "n_vaults": len(vaults),
            "total_tvl_usd": round(sum(tvls)),
            "n_over_10m": sum(1 for t in tvls if t >= 10e6),
            "n_over_5m": sum(1 for t in tvls if t >= 5e6),
            "max_tvl": round(max(tvls)) if tvls else 0,
        }
        print(f"[morpho] ethereum vaults={len(vaults)} total_tvl=${res['ethereum']['total_tvl_usd']:,} "
              f">=10M:{res['ethereum']['n_over_10m']}")
    except Exception as e:  # noqa: BLE001
        res["ethereum"] = {"error": repr(e)[:200]}
        print("[morpho] ethereum ERROR:", repr(e)[:160])
    try:
        base = morpho.vaults((8453,), first=50)
        res["base"] = {"n_vaults": len(base), "feasible": True}
        print(f"[morpho] base vaults={len(base)} (feasible)")
    except Exception as e:  # noqa: BLE001
        res["base"] = {"error": repr(e)[:160], "feasible": False}
        print("[morpho] base ERROR:", repr(e)[:160])
    return res


def probe_pendle() -> dict:
    try:
        data = pendle.markets_active(1)
        mkts = data.get("markets", [])
        liq = [((m.get("details") or {}).get("liquidity") or 0) for m in mkts]
        res = {
            "n_markets": len(mkts),
            "total_liquidity_usd": round(sum(liq)),
            "n_over_1m": sum(1 for x in liq if x >= 1e6),
            "n_over_5m": sum(1 for x in liq if x >= 5e6),
        }
        print(f"[pendle] active markets={len(mkts)} total_liq=${res['total_liquidity_usd']:,} "
              f">=1M:{res['n_over_1m']}")
        return res
    except Exception as e:  # noqa: BLE001
        print("[pendle] ERROR:", repr(e)[:160])
        return {"error": repr(e)[:200]}


def main() -> None:
    print("=== EVENT PRICE-SERIES PROBE ===")
    events = probe_events()
    print("\n=== MARKET-SCAN UNIVERSE PROBE ===")
    mo = probe_morpho()
    pe = probe_pendle()

    usable = [e for e in events if e["usable"]]
    print(f"\nUsable events: {len(usable)} / {len(events)}  (floor is 4)")
    report = {"events": events, "n_usable": len(usable), "morpho": mo, "pendle": pe}
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / "probe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("wrote artifacts/probe.json")


if __name__ == "__main__":
    main()
