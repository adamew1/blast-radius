"""Shared Streamlit UI helpers: verdict card, metric row, formatting."""
from __future__ import annotations

import re

import streamlit as st


def _md_bold_to_html(s: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)

VERDICT_STYLE = {
    "STAY":   ("#1b7f3b", "#e8f6ec", "✅"),
    "REDUCE": ("#b8860b", "#fdf5e3", "⚠️"),
    "EXIT":   ("#c0392b", "#fdecea", "🚪"),
}


def pct(x: float, dp: int = 2) -> str:
    return f"{x * 100:.{dp}f}%"


def usd(x: float) -> str:
    return f"${x:,.0f}"


def verdict_card(decision: dict) -> None:
    v = decision["verdict"]
    border, bg, icon = VERDICT_STYLE.get(v, ("#555", "#eee", "•"))
    st.markdown(
        f"""
        <div style="border-left:8px solid {border};background:{bg};padding:16px 20px;
                    border-radius:8px;margin:4px 0 10px 0;">
          <div style="font-size:30px;font-weight:800;color:{border};letter-spacing:0.5px;">
            {icon}&nbsp;{v}</div>
          <div style="color:#222;font-size:15px;margin-top:6px;line-height:1.5;">
            {_md_bold_to_html(decision['reason'])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_row(decision: dict) -> None:
    c = st.columns(5)
    c[0].metric("Exp. loss", pct(decision["el"]), help="Monte-Carlo mean loss over the horizon")
    c[1].metric("CVaR-95", pct(decision["cvar95"]), help="Mean loss in the worst 5% of paths")
    c[2].metric("Carry", pct(decision["carry"]), help="Yield earned over the horizon")
    c[3].metric("Exit cost", pct(decision["exit_cost"], 3) if decision.get("exit_available", True) else "Unavailable",
                help="Captured quote valuation plus assumed reserves; future execution is not guaranteed")
    delta = decision["net_stay"]
    c[4].metric("Net (stay)", pct(delta), delta=pct(delta),
                help="Carry minus expected loss (expected P&L if you hold)")
