"""Tab 2 — Portfolio: a book of up to 10 positions -> shared dependencies -> ranked actions."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from app.components.ui import pct, usd  # noqa: E402
from blast_radius.portfolio.book import analyze_book, load_book  # noqa: E402

st.set_page_config(page_title="Portfolio · Blast Radius", page_icon="💥", layout="wide")
st.title("Portfolio — shared dependencies & ranked actions")

with st.sidebar:
    st.header("Book")
    up = st.file_uploader("Upload a book (JSON or CSV)", type=["json", "csv"])
    n_paths = st.select_slider("Monte-Carlo paths / position", [4_000, 8_000, 16_000], value=8_000)
    st.caption("No file → the bundled 10-position sample book is used.")

if up is not None:
    if up.name.endswith(".csv"):
        positions = pd.read_csv(up).to_dict(orient="records")
    else:
        doc = json.load(up)
        positions = doc.get("positions", doc)
    book_name = up.name
else:
    bk = load_book()
    positions, book_name = bk["positions"], bk.get("name", "sample book")


@st.cache_data(show_spinner=False)
def run(book_json: str, np_: int):
    return analyze_book(json.loads(book_json), n_paths=np_)


with st.spinner(f"Analysing {len(positions)} positions…"):
    res = run(json.dumps(positions), n_paths)

t = res["totals"]
st.markdown((f"**{book_name}** — {t['positions']} positions · {usd(t['aum_usd'])} AUM")
            .replace("$", "\\$"))

verd = {}
for r in res["per_position"]:
    verd[r["verdict"]] = verd.get(r["verdict"], 0) + 1
c = st.columns(4)
c[0].metric("Expected loss (horizon)", usd(t["expected_loss_usd"]), delta=pct(t["expected_loss_pct"]),
            delta_color="inverse")
c[1].metric("EXIT", verd.get("EXIT", 0))
c[2].metric("REDUCE", verd.get("REDUCE", 0))
c[3].metric("STAY", verd.get("STAY", 0))

# ---------------- shared dependencies ----------------
st.subheader("Shared dependencies across the book")
non_chain = [e for e in res["shared"] if e["kind"] != "chain"]
if non_chain:
    top = non_chain[0]
    st.warning(
        f"**Concentration risk:** {top['count']} of {t['positions']} positions depend on "
        f"**{top['label']}** ({top['kind']}). A single failure there hits "
        f"{top['count']} positions at once — correlated loss the per-position view hides.")
    cols = st.columns(min(4, len(non_chain)))
    for col, e in zip(cols, non_chain[:4]):
        col.metric(e["label"], f"{e['count']} / {t['positions']}", help=f"shared {e['kind']}")

# ---------------- heatmap ----------------
hm = res["heatmap"]
if hm["cols"]:
    st.subheader("Position × dependency exposure")
    st.caption("Cell = transmission: how much of each position's value a failure in that dependency "
               "would reach (0 = not exposed).")
    fig = px.imshow(hm["matrix"], x=hm["cols"], y=hm["rows"], color_continuous_scale="YlOrRd",
                    aspect="auto", labels=dict(color="transmission"), zmin=0, zmax=1)
    fig.update_layout(height=60 + 34 * len(hm["rows"]), margin=dict(l=10, r=10, t=10, b=10),
                      xaxis=dict(side="top", tickangle=-35))
    st.plotly_chart(fig, use_container_width=True)

# ---------------- ranked actions ----------------
st.subheader("Ranked actions (worst risk-adjusted first)")
rank_df = pd.DataFrame([{
    "Position": r["label"], "Call": r["verdict"],
    "Exp. loss": pct(r["el"], 1), "Carry": pct(r["carry"], 1),
    "Net (stay)": pct(r["net_stay"], 1), "Exit cost": pct(r["exit_cost"], 2),
    "Dominant risk path": r["dominant_path"],
} for r in res["ranking"]])


def _hi(row):
    color = {"EXIT": "#fdecea", "REDUCE": "#fdf5e3", "STAY": "#e8f6ec"}.get(row["Call"], "")
    return [f"background-color: {color}"] * len(row)


st.dataframe(rank_df.style.apply(_hi, axis=1), hide_index=True, use_container_width=True)
st.caption("Net (stay) = carry − expected loss. Negative ⇒ you are not being paid for the risk.")
