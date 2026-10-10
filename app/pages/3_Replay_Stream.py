"""Tab 3 — Replay: Stream Finance → Elixir deUSD contagion (November 2025).

Real DefiLlama price series drive a day-by-day replay. The verdict is computed from information
visible on each day (the upstream xUSD shock propagated to the sdeUSD holding), and the avoided
loss is computed from the real sdeUSD price at the EXIT signal vs the end.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import datetime as _dt  # noqa: E402

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from app.components.graphviz import build_figure  # noqa: E402
from app.components.ui import pct, verdict_card  # noqa: E402
from blast_radius.replay.stream import build_graph, compute_frames, load_snapshot  # noqa: E402


def _short(date_str: str) -> str:
    return _dt.datetime.strptime(date_str, "%Y-%m-%d").strftime("%b %d")

st.set_page_config(page_title="Replay · Stream Finance", page_icon="💥", layout="wide")

st.title("Replay — Stream Finance → Elixir deUSD contagion")
st.caption("November 2025 · real DefiLlama price series · reconstructed dependency structure (sourced)")
st.caption("Development case: the rule was built knowing this outcome. Nov 1–3 REDUCE follows "
           "from zero carry (APY=0): any positive expected loss makes net_stay negative; EXIT "
           "requires clearing the assumed 1% exit cost. The 99.7% hero figure is a gross daily "
           "price comparison before transaction costs, not an executed trade.")

snap = load_snapshot()
data = compute_frames()
frames = data["frames"]
hero = data["hero"]
g = build_graph(snap)

st.markdown(
    "You hold **$1,000,000 of Elixir sdeUSD**. On the surface it is a yield-bearing dollar at peg. "
    "Underneath, ~**65% of deUSD's backing was a loan to Stream Finance**, collateralised by Stream's "
    "xUSD. Blast Radius discovers that hidden chain — and watches the **upstream** asset."
)

# ---------------- hero ----------------
if hero.get("signal_date"):
    c = st.columns(4)
    c[0].metric("Blast Radius says EXIT", _short(hero["signal_date"]),
                help="First day the propagated upstream shock exceeds the 1% exit cost")
    c[1].metric("sdeUSD price that day", f"\\${hero['sdeusd_signal']:.3f}",
                help="Still essentially at peg — the collapse hasn't reached it yet")
    c[2].metric("Avoided loss (exit on signal)", pct(hero["avoided_loss_pct"], 1),
                delta=f"vs holding to \\${hero['sdeusd_end']:.3f}", delta_color="inverse")
    c[3].metric("Lead over price-watchers", f"{hero['lead_days']} days",
                help=f"A naive price-watcher only exits {hero['naive_exit_date']} "
                     f"at \\${hero['sdeusd_naive']:.3f} — already {pct(hero['naive_loss_pct'],0)} down")
    st.success(
        f"**The point:** a dependency-aware desk exits sdeUSD on **{_short(hero['signal_date'])}** at "
        f"**\\${hero['sdeusd_signal']:.2f}** — {hero['lead_days']} days before it collapses to "
        f"**\\${hero['sdeusd_end']:.3f}**. Watching sdeUSD's own price, you don't react until "
        f"**{_short(hero['naive_exit_date'])}**, after a {pct(hero['naive_loss_pct'],0)} loss.")

st.divider()

# ---------------- timeline ----------------
dates = data["dates"]
default_idx = dates.index(data["first_exit"]) if data.get("first_exit") in dates else 0
sel = st.select_slider("Replay day", options=dates, value=dates[default_idx])
fr = next(f for f in frames if f["date"] == sel)

left, right = st.columns([1, 1.15])
with left:
    verdict_card({"verdict": fr["verdict"], "reason": fr["reason"]})
    st.markdown(f"**{sel}** — {fr['narrative']}")
    m = st.columns(3)
    for col, name in zip(m, ["xUSD", "deUSD", "sdeUSD"]):
        p = fr["prices"].get(name)
        base = snap["baseline"][name]
        dev = (p / base - 1) if p else None
        col.metric(name, f"\\${p:.3f}" if p else "—",
                   delta=f"{dev*100:+.0f}% vs peg" if dev is not None else None,
                   delta_color="inverse")
    mm = st.columns(2)
    mm[0].metric("Upstream xUSD shock", pct(fr["xusd_shock"], 0))
    mm[1].metric("Propagated expected loss", pct(fr["el"], 1))

with right:
    fig = go.Figure()
    for name, color in [("xUSD", "#c0392b"), ("deUSD", "#2e86de"), ("sdeUSD", "#8e44ad")]:
        base = snap["baseline"][name]
        xs, ys = [], []
        for f in frames:
            p = f["prices"].get(name)
            if p is not None:
                xs.append(f["date"]); ys.append(100 * p / base)
        fig.add_trace(go.Scatter(x=xs, y=ys, name=name, mode="lines", line=dict(color=color, width=2)))
    fig.add_vline(x=sel, line_color="#333", line_dash="dot")
    if hero.get("signal_date"):
        fig.add_vline(x=hero["signal_date"], line_color="#1b7f3b",
                      annotation_text="EXIT signal", annotation_position="top left")
    fig.update_layout(height=380, yaxis_title="% of pre-event peg", margin=dict(l=10, r=10, t=10, b=10),
                      legend=dict(orientation="h", y=1.02, yanchor="bottom"))
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Dependency graph on this day")
st.caption("Node colour = share of the position's expected loss on the selected day. "
           "xUSD (upstream origin) highlighted. All edges are reconstructed from sourced analyses.")
st.plotly_chart(build_figure(g, node_shares=fr["shares"], highlight={"token:xusd"}),
                use_container_width=True)

with st.expander("Sources (dependency structure reconstructed from these)"):
    for s in data["sources"]:
        st.markdown(f"- {s}")
    st.caption("Price series (xUSD/deUSD/sdeUSD) are real daily DefiLlama series, cached in data/raw/.")
