"""Per-kind resolvers: expand one node into its immediate dependencies (nodes + typed edges).

Every edge records where its fact came from (`api:pendle` / `api:morpho` / `api:defillama`
/ `manual`) so the UI can badge manual facts. The recursive engine (engine.py) walks the
token nodes these resolvers emit until it reaches base assets or the settlement chain.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

from ..config import manual_map
from ..sources import morpho, pendle
from .graph import DependencyGraph, Edge, Node

ETH = "ethereum"


@dataclass
class Context:
    chain_id: int = 1
    chain_name: str = ETH
    _pt_index: Optional[dict] = field(default=None, repr=False)
    _morpho_vaults: Optional[list] = field(default=None, repr=False)
    # Explicit run-local inputs. Snapshot callers retain the original clients.
    provider: object | None = field(default=None, repr=False)
    mappings: dict | None = field(default=None, repr=False)

    def markets_active(self):
        return (self.provider or pendle).markets_active(self.chain_id)

    @property
    def pt_index(self) -> dict:
        """raw PT address (lowercased) -> market dict."""
        if self._pt_index is None:
            self._pt_index = {}
            for m in self.markets_active().get("markets", []):
                self._pt_index[_raw(m["pt"])] = m
        return self._pt_index

    @property
    def morpho_vaults(self) -> list:
        if self._morpho_vaults is None:
            self._morpho_vaults = (self.provider or morpho).vaults((self.chain_id,), first=50)
        return self._morpho_vaults


def _raw(addr: str) -> str:
    a = addr.split("-", 1)[1] if addr and "-" in addr else (addr or "")
    return a.lower()


# -------- id helpers (canonical, so shared deps collapse to one node across positions) ------
def chain_id_node(name: str) -> str:
    return f"chain:{name}"


def token_id(addr: str, chain: str = ETH) -> str:
    return f"token:{chain}:{addr.lower()}"


def _manual_token(addr: str, ctx: Context) -> dict:
    return ((ctx.mappings if ctx.mappings is not None else manual_map()).get("tokens") or {}).get(addr.lower(), {})


def _manual_issuer(key: str, ctx: Context) -> dict:
    return ((ctx.mappings if ctx.mappings is not None else manual_map()).get("issuers") or {}).get(key, {})


def _add_chain(g: DependencyGraph, parent_id: str, ctx: Context, source: str) -> None:
    cid = chain_id_node(ctx.chain_name)
    cinfo = ((ctx.mappings if ctx.mappings is not None else manual_map()).get("chains") or {}).get(ctx.chain_name, {})
    g.add_node(Node(id=cid, kind="chain", label=ctx.chain_name.title(), chain=ctx.chain_name,
                    meta={"risk_category": cinfo.get("risk_category", "Chain"),
                          "source": cinfo.get("source")}))
    g.add_edge(Edge(parent=parent_id, child=cid, dep_type="chain", exposure_pct=100.0, source=source))


def _add_token_node(g: DependencyGraph, addr: str, ctx: Context) -> str:
    """Create (idempotently) a token node from the manual map / PT index and return its id."""
    tid = token_id(addr, ctx.chain_name)
    if g.has_node(tid) and g.node(tid).meta.get("resolved_label"):
        return tid
    mt = _manual_token(addr, ctx)
    is_pt = addr.lower() in ctx.pt_index
    label = mt.get("symbol") or (ctx.pt_index[addr.lower()]["name"] + " PT" if is_pt else addr[:8])
    risk_cat = "Yield" if is_pt else mt.get("risk_category")
    g.add_node(Node(id=tid, kind="token", label=label, chain=ctx.chain_name,
                    price_key=f"{ctx.chain_name}:{addr.lower()}",
                    meta={"address": addr.lower(), "risk_category": risk_cat,
                          "is_pendle_pt": is_pt, "peg": mt.get("peg"),
                          "source": mt.get("source"), "resolved_label": label,
                          "mapped": bool(mt) or is_pt}))
    return tid


# ---------------------------------- resolvers ---------------------------------------------
def resolve_pendle_pt(g: DependencyGraph, pos: Node, ctx: Context, position: dict) -> list[str]:
    cid = position.get("chain_id", 1)
    market = position["market"]
    markets = ctx.markets_active().get("markets", [])
    m = next((x for x in markets if x["address"].lower() == market.lower()), None)
    if not m:
        return []
    # Scans supply the cached universe snapshot; avoid a redundant per-market request.
    md = {} if position.get("market_snapshot") else ((ctx.provider or pendle).market_data(market, cid) or {})
    details = m.get("details") or {}
    pos.meta.update({
        "risk_category": "Yield",
        "protocol": "Pendle V2",
        "apy": details.get("impliedApy") or 0.0,
        "expiry": m.get("expiry"),
        "pt": m["pt"], "sy": m["sy"], "underlying": m["underlyingAsset"],
        "market": market,
        "liquidity_usd": details.get("liquidity") or (md.get("liquidity") or {}).get("usd"),
    })

    recurse: list[str] = []
    _add_chain(g, pos.id, ctx, source="api:pendle")

    # Layer: PT market & its AMM curve (the exit-liquidity venue).
    amm_id = f"amm:pendle:{market.lower()}"
    g.add_node(Node(id=amm_id, kind="amm", label=f"Pendle {m['name']} pool", chain=ctx.chain_name,
                    meta={"risk_category": "Dexs", "protocol": "Pendle V2",
                          "liquidity_usd": details.get("liquidity"),
                          "market": market, "pt": m["pt"], "underlying": m["underlyingAsset"],
                          "source": "api:pendle"}))
    g.add_edge(Edge(pos.id, amm_id, dep_type="liquidity", exposure_pct=100.0, source="api:pendle",
                    note="PT exits route through this Pendle AMM"))

    # Layer: underlying yield source (SY -> underlying) and, by recursion, its issuer & oracle.
    und = _add_token_node(g, _raw(m["underlyingAsset"]), ctx)
    g.add_edge(Edge(pos.id, und, dep_type="backing", exposure_pct=100.0, source="api:pendle",
                    note="PT is a claim on the underlying at maturity"))
    recurse.append(und)

    # Layer: lending markets that hold this PT as collateral (contagion / forced-liquidation).
    held = [h for h in _morpho_markets_holding(ctx, _raw(m["pt"])) if (h.get("supply_usd") or 0) >= 1000]
    liq = details.get("liquidity") or 0.0
    for mk in held[:3]:
        lmkt_id = f"lmkt:morpho:{mk['marketId']}"
        st = mk.get("state") or {}
        lltv_pct = int(mk.get("lltv") or 0) / 1e18
        g.add_node(Node(id=lmkt_id, kind="lending_market",
                        label=f"Morpho {mk['loan_symbol']}/{mk['collat_symbol']} @{lltv_pct:.0%}", chain=ctx.chain_name,
                        meta={"risk_category": "Lending", "protocol": "Morpho Blue",
                              "lltv": mk["lltv"], "utilization": st.get("utilization"),
                              "supply_usd": mk.get("supply_usd"),
                              "liquidity_usd": st.get("liquidityAssetsUsd"), "source": "api:morpho"}))
        expo = min(100.0, 100.0 * (mk.get("supply_usd") or 0.0) / liq) if liq else 20.0
        g.add_edge(Edge(pos.id, lmkt_id, dep_type="liquidity", exposure_pct=round(expo, 1),
                        source="api:morpho",
                        note="forced liquidations here dump PT into the AMM, depressing its price"))
        _add_market_oracle(g, lmkt_id, mk)
    return recurse


def resolve_morpho_vault(g: DependencyGraph, pos: Node, ctx: Context, position: dict) -> list[str]:
    cid = position.get("chain_id", 1)
    v = position.get("vault_snapshot") or (ctx.provider or morpho).vault_by_address(position["vault"], cid)
    if not v:
        return []
    state = v.get("state") or {}
    total = state.get("totalAssetsUsd") or 0.0
    pos.meta.update({
        "risk_category": "Lending", "protocol": f"Morpho · {v.get('name')}",
        "apy": state["netApy"] if state.get("netApy") is not None else (state.get("apy") or 0.0),
        "asset": (v.get("asset") or {}).get("symbol"),
        "tvl_usd": total, "n_markets": len(state.get("allocation") or []),
    })
    _add_chain(g, pos.id, ctx, source="api:morpho")

    recurse: list[str] = []
    allocs = sorted(state.get("allocation") or [], key=lambda a: a.get("supplyAssetsUsd") or 0, reverse=True)
    for a in allocs:
        mk = a.get("market") or {}
        if not mk.get("collateralAsset"):
            continue  # idle / loan-only allocation
        st = mk.get("state") or {}
        supply = a.get("supplyAssetsUsd") or 0.0
        expo = round(100.0 * supply / total, 2) if total else 0.0
        if supply <= 0 or expo < 0.1:
            continue  # declutter: skip dust / idle-configured markets
        collat = mk["collateralAsset"]
        lltv_pct = int(mk.get("lltv") or 0) / 1e18
        lmkt_id = f"lmkt:morpho:{mk['marketId']}"
        g.add_node(Node(id=lmkt_id, kind="lending_market",
                        label=f"Morpho {(mk.get('loanAsset') or {}).get('symbol')}/{collat.get('symbol')} @{lltv_pct:.0%}",
                        chain=ctx.chain_name,
                        meta={"risk_category": "Lending", "protocol": "Morpho Blue",
                              "lltv": mk.get("lltv"), "utilization": st.get("utilization"),
                              "supply_usd": supply, "liquidity_usd": st.get("liquidityAssetsUsd"),
                              "collateral_symbol": collat.get("symbol"), "source": "api:morpho"}))
        g.add_edge(Edge(pos.id, lmkt_id, dep_type="collateral", exposure_pct=expo, source="api:morpho",
                        note=f"{expo:.1f}% of vault supplied to this market"))
        # collateral token (recurses: PT -> underlying -> issuer, or wrapper -> backing -> issuer)
        ctok = _add_token_node(g, (collat.get("address") or "").lower(), ctx)
        if not g.node(ctok).meta.get("mapped"):
            g.node(ctok).label = collat.get("symbol") or g.node(ctok).label
        g.add_edge(Edge(lmkt_id, ctok, dep_type="collateral", exposure_pct=100.0, source="api:morpho"))
        recurse.append(ctok)
        _add_market_oracle(g, lmkt_id, {"marketId": mk["marketId"],
                                        "oracle": (mk.get("oracle") or {}).get("address")})
    return recurse


def resolve_token(g: DependencyGraph, node: Node, ctx: Context) -> list[str]:
    """Unwrap a token: Pendle PT -> underlying + AMM; wrapper -> backing; else issuer/oracle/terminal."""
    addr = node.meta["address"]
    recurse: list[str] = []

    # Pendle PT held as collateral -> unwrap into its underlying + AMM.
    if node.meta.get("is_pendle_pt"):
        m = ctx.pt_index[addr]
        amm_id = f"amm:pendle:{m['address'].lower()}"
        g.add_node(Node(id=amm_id, kind="amm", label=f"Pendle {m['name']} pool", chain=ctx.chain_name,
                        meta={"risk_category": "Dexs", "protocol": "Pendle V2",
                              "liquidity_usd": (m.get("details") or {}).get("liquidity"),
                              "market": m["address"], "source": "api:pendle"}))
        g.add_edge(Edge(node.id, amm_id, dep_type="liquidity", exposure_pct=100.0, source="api:pendle"))
        und = _add_token_node(g, _raw(m["underlyingAsset"]), ctx)
        g.add_edge(Edge(node.id, und, dep_type="backing", exposure_pct=100.0, source="api:pendle"))
        return [und]

    mt = _manual_token(addr, ctx)
    if mt.get("opaque"):
        node.meta["unmapped"] = True
    node.meta["estimated"] = bool(mt.get("estimated"))
    # issuer
    if mt.get("issuer"):
        iss = _manual_issuer(mt["issuer"], ctx)
        iid = f"issuer:{mt['issuer']}"
        g.add_node(Node(id=iid, kind="issuer", label=iss.get("name", mt["issuer"]), chain=ctx.chain_name,
                        meta={"risk_category": iss.get("risk_category"),
                              "protocol": iss.get("defillama_slug"), "source": iss.get("source"),
                              "mapped": True}))
        g.add_edge(Edge(node.id, iid, dep_type="issuer", exposure_pct=100.0, source="manual",
                        note="off-chain / protocol issuer (manual)"))
    # oracle (manual asset oracle, where the token has one declared)
    if mt.get("oracle"):
        oc = mt["oracle"]
        oid = f"oracle:manual:{oc.get('name')}"
        g.add_node(Node(id=oid, kind="oracle", label=oc.get("name", "oracle"), chain=ctx.chain_name,
                        meta={"risk_category": "Oracle", "source": oc.get("source"), "mapped": True}))
        g.add_edge(Edge(node.id, oid, dep_type="oracle", exposure_pct=100.0, source="manual"))
    # backing (wrapper -> wrapped asset)
    wraps = mt.get("wraps")
    if wraps:
        child = _add_token_node(g, wraps.lower(), ctx)
        g.add_edge(Edge(node.id, child, dep_type="backing",
                        exposure_pct=float(mt.get("backing_share") or 100), source="manual",
                        note="backing asset (manual)"))
        recurse.append(child)
    else:
        # terminal asset: connect to the settlement chain
        _add_chain(g, node.id, ctx, source="manual" if mt else "manual")
        if not mt:
            node.meta["unmapped"] = True  # opaque collateral: flagged in UI
    return recurse


# ---------------------------------- helpers -----------------------------------------------
def _add_market_oracle(g: DependencyGraph, lmkt_id: str, mk: dict) -> None:
    addr = mk.get("oracle")
    if not addr:
        return
    oid = f"oracle:{addr.lower()}"
    g.add_node(Node(id=oid, kind="oracle", label=f"Oracle {addr[:10]}…", chain=ETH,
                    meta={"risk_category": "Oracle", "address": addr.lower(), "source": "api:morpho"}))
    g.add_edge(Edge(lmkt_id, oid, dep_type="oracle", exposure_pct=100.0, source="api:morpho"))


def _morpho_markets_holding(ctx: Context, token_addr: str) -> list[dict]:
    """Markets (across cached vaults) that use `token_addr` as collateral."""
    out: dict[str, dict] = {}
    for v in ctx.morpho_vaults:
        for a in ((v.get("state") or {}).get("allocation") or []):
            mk = a.get("market") or {}
            ca = (mk.get("collateralAsset") or {})
            if (ca.get("address") or "").lower() == token_addr:
                mid = mk.get("marketId")
                rec = out.setdefault(mid, {
                    "marketId": mid, "lltv": mk.get("lltv"),
                    "collat_symbol": ca.get("symbol"),
                    "loan_symbol": (mk.get("loanAsset") or {}).get("symbol"),
                    "state": mk.get("state") or {},
                    "oracle": (mk.get("oracle") or {}).get("address"),
                    "supply_usd": 0.0,
                })
                rec["supply_usd"] += a.get("supplyAssetsUsd") or 0.0
    return sorted(out.values(), key=lambda r: r["supply_usd"], reverse=True)
