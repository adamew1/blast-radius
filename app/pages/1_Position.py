"""Tab 1 — Position: input -> dependency graph -> risk -> verdict -> what-if."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # repo root

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from app.components.graphviz import build_figure  # noqa: E402
from app.components.ui import metric_row, pct, usd, verdict_card  # noqa: E402
from blast_radius.analyze import analyze_position  # noqa: E402
from blast_radius.config import load_config  # noqa: E402
from blast_radius.risk.propagate import top_contributors  # noqa: E402

st.set_page_config(page_title="Position · Blast Radius", page_icon="💥", layout="wide")
cfg = load_config()
positions = cfg["positions"]

st.title("Position risk & dependency look-through")
st.caption("Research model with assumed incident priors; not calibrated to the fire-drill shock probability. "
           "Execution uses frozen exact-size quotes or funded liquidity bounds. Unsupported exits require REVIEW.")

# ---------------- controls ----------------
with st.sidebar:
    st.header("Position")
    labels = [p["label"] for p in positions]
    pick = st.selectbox("Choose a snapshot instrument", labels)
    pos = dict(next(p for p in positions if p["label"] == pick))
    pos["size_usd"] = st.number_input("Position size (USD)", 10_000, 50_000_000,
                                      int(pos.get("size_usd", 500_000)), step=50_000)
    horizon = st.slider("Risk horizon (months)", 1, 24, int(cfg.get("horizon_months", 12)))
    n_paths = st.select_slider("Monte-Carlo paths", [5_000, 10_000, 20_000, 40_000], value=20_000)
    st.caption("Data cached from DefiLlama · Pendle · Morpho. Dashed graph edges = manual facts.")


@st.cache_data(show_spinner=False)
def run(pos_id, size, h, np_, force_tuple=None):
    p = dict(next(x for x in positions if x["id"] == pos_id))
    p["size_usd"] = size
    force = None
    if force_tuple:
        force = {force_tuple[0]: {"prob": 1.0, "severity": force_tuple[1]}}
    return analyze_position(p, horizon_months=h, n_paths=np_, force=force)


with st.spinner("Discovering dependencies and simulating failures…"):
    res = run(pos["id"], pos["size_usd"], horizon, n_paths)

g, risk, dec = res["graph"], res["risk"], res["decision"]

# ---------------- header & verdict ----------------
m = g.node(g.root_id).meta
sub = []
if m.get("apy"):
    sub.append(f"APY ≈ {pct(m['apy'])}")
if m.get("expiry"):
    sub.append(f"expiry {m['expiry'][:10]}")
if m.get("tvl_usd"):
    sub.append(f"vault TVL {usd(m['tvl_usd'])}")
sub.append(f"size {usd(pos['size_usd'])}")
st.markdown(f"**{pick}** — {' · '.join(sub)}")

verdict_card(dec)
metric_row(dec)

# ---------------- dependency graph ----------------
st.subheader("Dependency graph")
shares = {nid: (c / risk.el if risk.el else 0.0) for nid, c in risk.node_contrib.items()}
sm = res["summary"]
st.caption(
    f"{sm['nodes']} nodes · {sm['edges']} edges · "
    f"{sm['by_source'].get('api', 0)} cached-API / {sm['by_source'].get('manual', 0)} manual edges · "
    f"layers: {' → '.join(k for k in ['chain','issuer','oracle','token','amm','lending_market'] if k in sm['by_kind'])}"
)
st.plotly_chart(build_figure(g, node_shares=shares), use_container_width=True)

# ---------------- contributors + distribution ----------------
left, right = st.columns([1.1, 1])
with left:
    st.subheader("Where the expected loss comes from")
    rows = top_contributors(g, risk, k=8)
    df = pd.DataFrame([{
        "Dependency": r["node"], "Type": r["kind"],
        "Incident P (horizon)": pct(r["incident_prob"]),
        "Transmission": pct(r["transmission"], 0),
        "Share of exp. loss": pct(r["share_of_el"], 1),
    } for r in rows])
    st.dataframe(df, hide_index=True, use_container_width=True)
    if dec.get("dominant_path"):
        st.caption(f"Dominant risk path: **{dec['dominant_path']}**")

with right:
    st.subheader("Loss distribution over horizon")
    fig = px.histogram(x=risk.loss_samples * 100, nbins=60,
                       labels={"x": "position loss (%)"}, height=320)
    fig.add_vline(x=risk.el * 100, line_color="#b8860b",
                  annotation_text=f"EL {pct(risk.el)}", annotation_position="top")
    fig.add_vline(x=risk.cvar95 * 100, line_color="#c0392b",
                  annotation_text=f"CVaR95 {pct(risk.cvar95)}", annotation_position="top")
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), showlegend=False,
                      yaxis_title="paths")
    st.plotly_chart(fig, use_container_width=True)

# ---------------- what-if ----------------
st.subheader("What-if: force a dependency to fail")
node_opts = {f"{g.node(n).label}  ·  {g.node(n).kind}": n
             for n in g.g.nodes if n != g.root_id}
wc1, wc2, wc3 = st.columns([2, 1, 1])
sel = wc1.selectbox("Dependency", list(node_opts.keys()))
sev = wc2.slider("Severity of failure", 0.1, 1.0, 0.8, 0.05)
go_wif = wc3.toggle("Simulate failure")
if go_wif:
    nid = node_opts[sel]
    wif = run(pos["id"], pos["size_usd"], horizon, n_paths, force_tuple=(nid, sev))
    wdec = wif["decision"]
    d1, d2, d3 = st.columns(3)
    d1.metric("Expected loss", pct(wdec["el"]), delta=pct(wdec["el"] - dec["el"]))
    d2.metric("CVaR-95", pct(wdec["cvar95"]), delta=pct(wdec["cvar95"] - dec["cvar95"]))
    d3.metric("Verdict", wdec["verdict"],
              delta=None if wdec["verdict"] == dec["verdict"] else f"was {dec['verdict']}")
    verdict_card(wdec)
    st.plotly_chart(
        build_figure(wif["graph"],
                     node_shares={k: (c / wif["risk"].el if wif["risk"].el else 0)
                                  for k, c in wif["risk"].node_contrib.items()},
                     highlight={nid}),
        use_container_width=True)

# ---------------- provenance ----------------
with st.expander("Dependency provenance (data sources & manual facts)"):
    st.write("**Live-API facts** come from DefiLlama, Pendle, and Morpho. "
             "**Manual facts** (dashed edges) are issuer/oracle/backing links the public APIs "
             "do not expose; each has a source link below.")
    manual_rows = []
    for e in g.edges():
        if e.is_manual:
            child = g.node(e.child)
            manual_rows.append({"Dependency": f"{g.node(e.parent).label} → {child.label}",
                                "Type": e.dep_type, "Source": child.meta.get("source", "manual")})
    if manual_rows:
        st.dataframe(pd.DataFrame(manual_rows), hide_index=True, use_container_width=True)
    opaque = [g.node(n).label for n in g.g.nodes if g.node(n).meta.get("unmapped")]
    if opaque:
        st.warning("Backing not yet mapped (shown as opaque, no deep look-through): "
                   + ", ".join(sorted(set(opaque))))
