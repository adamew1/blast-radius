"""Local, buildless Streamlit v2 component. Financial values come from Python."""
from pathlib import Path
import hashlib

import streamlit as st
import streamlit.components.v2 as components

ASSETS = Path(__file__).parent / "terminal"


def terminal_component(css: str, js: str):
    digest = hashlib.sha256((css + js).encode()).hexdigest()[:12]
    return components.component("blast_radius_terminal_" + digest,
                                html='<div id="terminal"></div>',
                                css=css, js=js)


def render_terminal(payload: dict, key="risk_terminal"):
    return terminal_component((ASSETS / "terminal.css").read_text(encoding="utf-8"),
                              (ASSETS / "terminal.js").read_text(encoding="utf-8"))(
                                data=payload, key=key, height="content",
                                on_action_change=lambda: None)
