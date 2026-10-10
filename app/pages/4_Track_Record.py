"""Tab 4 — Track Record: a frozen signal rule backtested over real upstream->downstream
contagions. Every number is read from artifacts/backtest_results.json (computed by
scripts/run_backtest.py from cached real DefiLlama data). Misses and false alarms are shown
as prominently as hits; the Stream case the rule was built on is reported separately."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from app.components.ui import usd  # noqa: E402

st.set_page_config(page_title="Track Record · Blast Radius", page_icon="💥", layout="wide")

ART = pathlib.Path(__file__).resolve().parents[2] / "artifacts" / "backtest_results.json"
if not ART.exists():
    st.error("artifacts/backtest_results.json not found — run `python scripts/run_backtest.py`.")
    st.stop()
data = json.loads(ART.read_text(encoding="utf-8"))

st.title("Track Record — does the signal generalise?")
st.caption("One frozen rule (declared in data/backtest/signal_rule.yaml) applied identically to "
           "real upstream→downstream contagions · prices are cached real DefiLlama series · "
           "misses and false alarms reported as prominently as hits.")

h = data["headline"]["without_stream"]
dev = data["headline"]["development_case"]
fa = data["false_alarms"]
sc = fa["by_upstream_kind"]["stablecoin"]
vo = fa["by_upstream_kind"]["volatile"]

st.markdown(
    "The **Stream → Elixir** collapse (the Replay tab) is one anecdote. Here the *same* rule — "
    "force the upstream's observed deviation into the engine, EXIT when expected loss clears the "
    "1% exit cost — is run over a selected library with usable price data. The rule's "
    "parameters were inherited from the Stream replay, so **Stream is the development case and is "
    "excluded from the headline below.**")

# ---------------- headline (without Stream = primary) ----------------
c = st.columns(4)
c[0].metric("Advance catches (excl. Stream)", f"{h['events_caught']}/{h['events_total']}",
            help="Signal fired EXIT strictly before the downstream fell >5%. Same-bar signals are misses. "
                 "Excludes the Stream development case.")
c[1].metric("Median lead time", f"{h['median_lead_hours']}h",
            delta=f"max {h['max_lead_hours']}h", delta_color="off",
            help="Tightly-coupled sympathy depegs give only hours; the multi-day lead appears "
                 "when the upstream breaks well before the downstream (see Stream below).")
c[2].metric("Saved vs naive price-watcher", usd(h["total_saved_vs_naive_usd"]).replace("$", "\\$"),
            help="All pairs, including misses. No EXIT: hold at observed worst-14d mark. "
                 "Indicative cached prices, assumed 1% exit cost, $1M per position; not executed P&L.")
c[3].metric("False alarms / pair-year (all)", f"{fa['per_pair_year']}",
            delta=f"{fa['n_pairs']} pairs", delta_color="off",
            help="2024 EXIT episodes with no >5% downstream break in the next 14 days. "
                 "A full 7-day reference and 14-day follow-up are required.")

st.info(
    f"**Honest read.** **{h['events_caught']} advance catches, {h['misses']} misses**, including "
    f"**{h['simultaneous_signals']} same-bar signals**, across {h['events_total']} pairs and "
    f"**{data['n_triggers_out_of_sample']} distinct crises** (excluding Stream). All-pair savings "
    f"vs the naive watcher: **{usd(h['total_saved_vs_naive_usd'])}**, including missed-exit hold marks. "
    f"Overall false-alarm rate: **{fa['per_pair_year']} per pair-year**. The descriptive breakdown is "
    f"**{sc['per_pair_year']}** for stablecoin upstreams and **{vo['per_pair_year']}** for the "
    f"volatile CRV proxy; this grouping was added after seeing the controls. "
    f"The **Stream development case** has median lead **{dev['median_lead_hours']}h** and "
    f"**{usd(dev['total_saved_vs_naive_usd'])}** saved vs naive."
    .replace("$", "\\$"))

incl = data["headline"]["with_stream"]
st.caption((f"Including Stream development pairs: {incl['events_caught']}/{incl['events_total']} "
            f"advance catches · median lead {incl['median_lead_hours']}h · "
            f"{usd(incl['total_saved_vs_naive_usd'])} saved vs naive. "
            f"Controls cover {fa['total_pair_years']:.3f} observed pair-years, not six full years; "
            "the six non-development pairs share upstream shocks and are not independent trials.")
           .replace("$", r"\$"))

st.divider()

# ---------------- results table (every event incl. misses) ----------------
st.subheader("Every event — including the misses")
rows = []
for e in sorted(data["events"], key=lambda x: (x["cohort"] == "development", x["date"])):
    exp = f"{e['exposure_pct']}%" + (" (est)" if e["estimated"] else "")
    rows.append({
        "Event": e["name"].replace(" [DEV CASE]", ""),
        "Date": e["date"],
        "Cohort": "DEV" if e["cohort"] == "development" else "retrospective",
        "Dependency": e["dep_type"],
        "Exposure": exp,
        "Result": "✅ advance" if e["hit"] else ("❌ MISS (same bar)" if e.get("simultaneous") else "❌ MISS"),
        "Lead (h)": f"{e['lead_hours']:g}" if e["lead_hours"] is not None else "—",
        "Downstm @ signal": f"{e['dn_at_signal']:.4f}" if e["dn_at_signal"] else "—",
        "Worst / 14d": f"{e['dn_worst_14d']:.4f}" if e["dn_worst_14d"] else "—",
        "Saved vs naive": usd(e["saved_vs_naive_usd"]) if e["saved_vs_naive_usd"] is not None else "—",
        "Naive loss": usd(e["naive_realized_loss_usd"]) if e["naive_realized_loss_usd"] is not None else "—",
        "Sources": " · ".join(e["sources"]),
    })
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
st.caption("‘Saved vs naive’ includes zero and negative outcomes. With no EXIT, the tool holds "
           "to the observed worst 14-day mark (unrealized). MIM was missed: its "
           "liquidity-type dependency transmits too weakly to fire before MIM’s own 5% break.")

# ---------------- false-alarm panel ----------------
st.subheader("False-alarm test — observed 2024 control windows, same rule")
fcols = st.columns([1.3, 1])
with fcols[0]:
    frows = [{"Pair": r["pair"], "Upstream": r.get("upstream_kind", "—"),
              "EXIT episodes": r["n_exit_episodes"], "False alarms": r["false_alarms"],
              "/ pair-year": r["false_alarms_per_pair_year"],
              "Observed pair-years": round(r["pair_years"], 3)}
             for r in fa["pairs"] if r.get("available")]
    st.dataframe(pd.DataFrame(frows), use_container_width=True, hide_index=True)
with fcols[1]:
    st.metric("Stablecoin-upstream pairs", f"{sc['per_pair_year']} / pair-yr",
              help=f"{sc['false_alarms']} false alarms over {sc['pair_years']:.3f} pair-years")
    st.metric("Volatile-token proxy", f"{vo['per_pair_year']} / pair-yr",
              delta="too noisy to trade", delta_color="inverse",
              help="A volatile governance token as upstream swings past the 1% gate constantly.")

st.divider()

# ---------------- per-event charts ----------------
st.subheader("One chart per event — upstream vs downstream, signal & break marked")


def chart(e: dict) -> go.Figure:
    ch = e["chart"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ch["t"], y=ch["up_pct"], name=f"{e['upstream']} (upstream)",
                             mode="lines", line=dict(color="#c0392b", width=2)))
    dn_name = f"{e['downstream']} (held)" + (" / ETH" if e["denom"] == "eth" else "")
    fig.add_trace(go.Scatter(x=ch["t"], y=ch["dn_pct"], name=dn_name, mode="lines",
                             line=dict(color="#2e86de", width=2)))
    fig.add_hline(y=95, line_color="#999", line_dash="dot",
                  annotation_text="-5% break", annotation_position="bottom left")
    if e["signal_date"]:
        fig.add_vline(x=e["signal_date"], line_color="#1b7f3b",
                      annotation_text="EXIT", annotation_position="top left")
    if e["break_date"]:
        fig.add_vline(x=e["break_date"], line_color="#b8860b", line_dash="dash",
                      annotation_text="break", annotation_position="top right")
    title = e["name"].replace(" [DEV CASE]", "") + (" · DEV CASE" if e["cohort"] == "development" else "")
    fig.update_layout(height=260, title=dict(text=title, font=dict(size=13)),
                      yaxis_title="% of reference", margin=dict(l=8, r=8, t=30, b=8),
                      showlegend=True, legend=dict(orientation="h", y=1.0, yanchor="bottom",
                                                   font=dict(size=9)))
    return fig


evs = sorted(data["events"], key=lambda x: (x["cohort"] == "development", x["date"]))
for i in range(0, len(evs), 2):
    cols = st.columns(2)
    for col, e in zip(cols, evs[i:i + 2]):
        col.plotly_chart(chart(e), use_container_width=True)

# ---------------- method & sources ----------------
with st.expander("Method, parameters & sources (nothing tuned on results)"):
    r = data["rule"]["rule"]
    st.markdown(
        f"- **Frozen rule:** exit cost {r['exit_cost_pct']*100:.0f}%, zero carry, "
        f"{r['horizon_months']}-month horizon, shock gate {r['shock_gate_pct']*100:.0f}%, "
        f"reference = {data['rule']['reference']['pre_event_median_days']}-day pre-event median "
        f"(rolling for controls). All inherited unchanged from the Stream replay.\n"
        f"- **Historical split:** retrospective event selection, not prospective validation. Pre-2024 caught "
        f"{data['split']['pre_2024']['events_caught']}/{data['split']['pre_2024']['events_total']}; "
        f"2024-25 (excl. Stream) caught "
        f"{data['split']['y2024_2025']['events_caught']}/{data['split']['y2024_2025']['events_total']}.\n"
        f"- **Limitations:** exposure shares are estimated (labelled), price granularity is 4h "
        f"(the finest DefiLlama returns for 2023), the USDC family shares one trigger, and CRV is a "
        f"proxy for Curve-ecosystem stress.")
    for note in data.get("scoring_notes", []):
        st.write("• " + note)
    st.caption("Cached spot prices and assumed execution costs cannot establish executable exits. "
               "No ML early-warning model is claimed; rule_vs_ml is null.")
    for e in evs:
        st.markdown(f"**{e['name']}** — exposure: {e['exposure_source']}")
        for s in e["sources"]:
            st.markdown(f"  - {s}")
