"""Ethereum market scan, rendered exclusively from the reproducible scan artifact."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import pandas as pd
import plotly.express as px
import streamlit as st
from app.components.ui import usd
from blast_radius.config import ARTIFACTS

st.set_page_config(page_title="Market Scan · Blast Radius", page_icon="💥", layout="wide")
st.title("Market Scan — shared dependencies across Ethereum")
path = ARTIFACTS / "market_scan.json"
if not path.exists():
    st.error("Run python scripts/run_market_scan.py to generate the cached scan.")
    st.stop()
d = json.loads(path.read_text(encoding="utf-8"))
c, coverage = d["config"], d["coverage"]
st.caption(f"Cached snapshot · Morpho listed vaults ≥ {usd(c['morpho_min_tvl_usd'])}; "
           f"active Pendle markets ≥ {usd(c['pendle_min_liquidity_usd'])} liquidity · "
           f"computed {d['generated_at'][:19]} UTC".replace("$", r"\$"))
st.caption("Source snapshots cached at: " + " · ".join(
    f"{name} {date[:19]} UTC" for name, date in d["universe"].get("source_cached_at", {}).items()))

cols = st.columns(4)
cols[0].metric("Gross TVL + liquidity scanned", usd(d["total_scanned_usd"]).replace("$", r"\$"))
cols[1].metric("Positions analysed", f"{d['n_positions']}/{d['n_eligible']}")
cols[2].metric("Mapped to declared depth", f"{coverage['fully_looked_through_pct']:.1f}%")
cols[3].metric("Scan compute time", f"{d['scan_wall_seconds']:.1f}s")

issuers = d["exposures"]["issuer"]
if issuers:
    top = issuers[0]
    st.info((f"Largest shared issuer dependency: **{top['label']}**, "
             f"**{usd(top['exposure_usd'])}** in transmission-weighted notional across "
             f"**{top['positions']} positions**. Top-three issuer concentration index: "
             f"**{d['top3_issuer_concentration']['share']:.1%}**. "
             "This is a model-weighted exposure index, not unique cash at risk.").replace("$", r"\$"))
    frame = pd.DataFrame(issuers[:15]).sort_values("exposure_usd")
    fig = px.bar(frame, x="exposure_usd", y="label", orientation="h",
                 labels={"exposure_usd": "Transmission-weighted notional (USD)", "label": "Issuer"},
                 hover_data=["positions"], color_discrete_sequence=["#2e86de"])
    fig.update_layout(height=470, margin=dict(l=5, r=10, t=5, b=5))
    st.plotly_chart(fig, width="stretch")

st.subheader("Ten highest modelled EL minus carry")
st.caption("12-month horizon; expected-loss ranking, not a recommendation to liquidate an entire "
           "vault or pool. Scan exit costs are estimates; the Position page retains executable-size quotes.")
st.dataframe(pd.DataFrame([{
    "Vault / market": r["label"], "Size (gross)": usd(r["size_usd"]),
    "EL − carry": f"{r['el_minus_carry']:.2%}", "Expected loss": f"{r['el']:.2%}",
    "Carry": f"{r['carry']:.2%}", "Dominant risk path": r["dominant_path"],
    "Mapped": "yes" if r["fully_looked_through"] else "partial / opaque",
} for r in d["top10"]]), hide_index=True, width="stretch")

st.subheader("Coverage and boundaries")
st.warning((f"**{coverage['opaque_pct']:.1f}% of scanned dollars** belong to positions with at "
            "least one unmapped discovered token. ‘Mapped’ means the graph reaches the declared "
            "issuer/base-asset depth; it does not establish complete reserves, counterparties, "
            "validator operators, or tranche waterfalls. All manual links are sourced. "
            "The universe is Ethereum only, limited to listed Morpho V1 vaults and active Pendle markets. "
            "Morpho loan-asset issuer risk is outside the discovered collateral graph. "
            "Gross vault TVL plus AMM liquidity can count the same capital more than once."))
if d["errors"]:
    st.error(f"{len(d['errors'])} eligible positions failed; denominator includes only successful analyses.")
if d["universe"]["morpho_page_full"]:
    st.warning("Morpho page limit reached; universe completeness is not established.")

with st.expander("Unmapped tokens and full methodology"):
    st.dataframe(pd.DataFrame(d["opaque_tokens"]), hide_index=True, width="stretch")
    st.write(coverage["definition"])
    st.write(d["top3_issuer_concentration"]["method"])
    for text in d["limitations"]:
        st.write("• " + text)
    st.json(c)
with st.expander("Token and oracle exposure tables"):
    for kind in ("token", "oracle"):
        st.write(kind.title())
        st.dataframe(pd.DataFrame(d["exposures"][kind]), hide_index=True, width="stretch")
st.download_button("Download complete scan", path.read_bytes(), "market_scan.json", "application/json")
