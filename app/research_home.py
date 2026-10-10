"""Blast Radius — Streamlit entry point (landing page)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # repo root on path

import json  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from blast_radius import __version__  # noqa: E402
from blast_radius.config import ARTIFACTS  # noqa: E402
from blast_radius.models.evaluation import comparison_text

st.set_page_config(page_title="Blast Radius", page_icon="💥", layout="wide")

st.title("💥 Blast Radius")
st.subheader("What is the blast radius of a DeFi position when one of its hidden dependencies fails?")

st.markdown(
    """
For an on-chain position, Blast Radius:

1. **Discovers hidden dependencies** — recursively unwraps a position to its settlement chain,
   underlying yield source & issuer, oracle, liquidity venue / AMM, and any lending market
   holding it as collateral.
2. **Propagates failure** — Monte-Carlo simulates incidents at each dependency and traces how the
   loss flows *up* the stack to your position (expected loss, CVaR-95, dominant risk path).
3. **Answers stay or exit** — compares expected loss from holding against the real cost of exiting
   (slippage / price impact) and returns a **STAY / REDUCE / EXIT** call with a plain-English reason.
"""
)

st.info(
    "Use the pages in the sidebar → **Position** (single position), **Portfolio** (a book of up to 10), "
    "**Replay: Stream Finance** (the development case), **Track Record** (including misses and "
    "false alarms), and **Market Scan** (Ethereum snapshot and mapping coverage).",
    icon="👈",
)

cols = st.columns(3)
cols[0].metric("Dependency discovery", "recursive look-through")
cols[1].metric("Impact", "Monte-Carlo propagation")
cols[2].metric("Decision", "STAY / REDUCE / EXIT")

bt_path, scan_path = ARTIFACTS / "backtest_results.json", ARTIFACTS / "market_scan.json"
if bt_path.exists() and scan_path.exists():
    bt = json.loads(bt_path.read_text(encoding="utf-8"))
    scan = json.loads(scan_path.read_text(encoding="utf-8"))
    h = bt["headline"]["without_stream"]
    st.subheader("Historical checks & Ethereum coverage")
    cc = st.columns(4)
    cc[0].metric("Advance catches, excluding Stream", f"{h['events_caught']}/{h['events_total']}")
    cc[1].metric("False alarms / observed pair-year", str(bt["false_alarms"]["per_pair_year"]))
    cc[2].metric("Gross TVL + liquidity scanned", f"\\${scan['total_scanned_usd']/1e6:.1f}M")
    cc[3].metric("Mapped to declared depth", f"{scan['coverage']['fully_looked_through_pct']:.1f}%")
    st.caption(f"{h['misses']} misses across {bt['n_triggers_out_of_sample']} non-development crises; "
               "retrospectively selected pairs and estimated exposures. Stream is the development case. "
               "Scan capital can overlap, and mapped issuers do not imply complete reserve look-through.")
    st.page_link("pages/4_Track_Record.py", label="Track Record — every pair and control window")
    st.page_link("pages/5_Market_Scan.py", label="Market Scan — concentrations and opaque positions")

st.divider()
st.subheader("Methodology & model evaluation (reported honestly)")


@st.cache_data(show_spinner=False)
def _severity_table():
    from blast_radius.models.severity import empirical_severity_table
    return empirical_severity_table()


@st.cache_data(show_spinner=False)
def _category_table():
    from blast_radius.models.incidents import category_table
    return category_table()


mcol1, mcol2 = st.columns(2)
with mcol1.expander("① Incident probability — model vs base-rate baseline", expanded=True):
    mp = ARTIFACTS / "metrics.json"
    if mp.exists():
        m = json.loads(mp.read_text(encoding="utf-8"))
        st.caption(f"{m['model_name']} on a {m['panel']['rows_total']:,}-row protocol×year panel "
                   f"(/hacks + /protocols). Time split: train {m['split']['train_years']}, "
                   f"test {m['split']['test_years']} · test positives {m['panel']['test_positives']} "
                   f"(prevalence {m['panel']['test_prevalence']*100:.2f}%).")
        st.dataframe(pd.DataFrame([
            {"": "Gradient-boosting model", **m["model"]},
            {"": "Category base-rate (baseline)", **m["baseline_category_rate"]},
        ]), hide_index=True, use_container_width=True)
        st.info(comparison_text(m["model"], m["baseline_category_rate"]) + ".")
        st.caption("TVL, audits, chain counts and the protocol catalog are current rather than "
                   "point-in-time features. This retrospective panel has look-ahead and survivorship limitations.")
    else:
        st.write("Run `python scripts/train_incident_model.py` to generate metrics.")

with mcol2.expander("② Loss severity by incident class (from /hacks)", expanded=True):
    st.caption("Empirical loss per hack classification. loss/TVL uses current TVL as a rough "
               "denominator (documented approximation); it informs the severity priors.")
    df = pd.DataFrame(_severity_table()[:8])
    df["median_loss_usd"] = df["median_loss_usd"].map(lambda x: f"${x:,.0f}")
    st.dataframe(df, hide_index=True, use_container_width=True)

with st.expander("③ Loss pass-through calibration (real Nov-2025 incidents)"):
    st.markdown(
        "- **Stream xUSD → Elixir deUSD:** on Nov 7, xUSD had lost ~87% and deUSD ~99%. With "
        "~65% of deUSD's backing exposed to Stream, the 'fundamental' loss ≈ 0.65 × 0.87 ≈ 57%; "
        "the market overshot to ~99% (an overshoot factor ≈ **1.7×** in a confidence-run). Our "
        "`backing` pass-through (0.95) is deliberately conservative vs this panic overshoot.\n"
        "- **Oracle:** a flat per-edge pass-through of **0.70**. LLTV is shown in labels; "
        "the liquidation helper is not called by propagation.\n"
        "- **AMM / liquidity:** flat pass-through **0.35** in propagation; "
        "the Position page separately estimates exit price impact.\n"
        "- Small-sample calibration (n≈3 documented 2025 events) — stated openly; priors + "
        "sensitivity, not false precision.")

with st.expander("④ Incident base rates by DefiLlama category"):
    st.caption("Annual per-protocol hazard and 12-month probability, from /hacks joined to "
               "/protocols. 'prior:depeg' rows blend a documented depeg prior for stablecoin-like "
               "classes that /hacks under-counts.")
    st.dataframe(pd.DataFrame(_category_table()).head(14), hide_index=True, use_container_width=True)

st.divider()
st.caption(
    f"Blast Radius v{__version__} · real data from DefiLlama, Pendle & Morpho (cached to disk). "
    "Manual/reconstructed facts are labelled in the UI. Research tool, not financial advice."
)
