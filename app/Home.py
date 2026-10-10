"""Blast Radius — Streamlit entry point (landing page)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # repo root on path

import streamlit as st  # noqa: E402

from blast_radius import __version__  # noqa: E402

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
    "and **Replay: Stream Finance** (a real Nov-2025 contagion, replayed on historical prices).",
    icon="👈",
)

cols = st.columns(3)
cols[0].metric("Dependency discovery", "recursive look-through")
cols[1].metric("Impact", "Monte-Carlo propagation")
cols[2].metric("Decision", "STAY / REDUCE / EXIT")

st.caption(
    f"Blast Radius v{__version__} · real data from DefiLlama, Pendle & Morpho (cached to disk). "
    "Manual/reconstructed facts are labelled in the UI."
)
