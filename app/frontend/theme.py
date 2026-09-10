"""
Phase 12 — shared dark theme for the modernization workspace.

Pure CSS/HTML injected via ``st.markdown(unsafe_allow_html=True)`` --
no new frontend framework or component-build pipeline, per the Phase 12
constraint to prefer Streamlit + HTML/CSS/SVG and avoid large frontend
dependencies introduced purely for visual effects.

This module only carries *presentation*. It has no opinion about
backend state -- callers (``landing.py``, ``mainframe.py``, ``app.py``)
decide what to render; this module only decides how it looks.
"""

from __future__ import annotations

import streamlit as st

# -- palette -----------------------------------------------------------
# near-black base, graphite panels, restrained cyan/teal illumination,
# amber for genuine warnings, red only for genuine failure.
BG = "#05070a"
PANEL = "#0d1117"
PANEL_BORDER = "#1c2733"
GRID_LINE = "#101820"
TEXT = "#e6edf3"
TEXT_MUTED = "#8b98a5"
CYAN = "#2dd4e8"
CYAN_DIM = "#134752"
TEAL = "#3ddc97"
AMBER = "#e8a92d"
RED = "#e84d4d"

BASE_CSS = f"""
<style>
  :root {{
    --mf-bg: {BG};
    --mf-panel: {PANEL};
    --mf-border: {PANEL_BORDER};
    --mf-grid: {GRID_LINE};
    --mf-text: {TEXT};
    --mf-muted: {TEXT_MUTED};
    --mf-cyan: {CYAN};
    --mf-cyan-dim: {CYAN_DIM};
    --mf-teal: {TEAL};
    --mf-amber: {AMBER};
    --mf-red: {RED};
  }}

  html, body, [data-testid="stApp"] {{
    background-color: var(--mf-bg) !important;
    color: var(--mf-text);
  }}
  [data-testid="stAppViewContainer"] {{
    background:
      radial-gradient(circle at 15% 0%, rgba(45,212,232,0.06), transparent 45%),
      var(--mf-bg);
  }}
  [data-testid="stHeader"] {{
    background: transparent !important;
  }}
  [data-testid="stSidebar"] {{
    background-color: var(--mf-panel) !important;
    border-right: 1px solid var(--mf-border);
  }}
  [data-testid="stSidebar"] * {{
    color: var(--mf-text);
  }}

  h1, h2, h3, h4, h5, h6, p, span, label, div {{
    color: var(--mf-text);
  }}
  .mf-muted {{ color: var(--mf-muted) !important; }}

  /* buttons: quiet by default, cyan on hover -- no rainbow gradients */
  .stButton > button, .stDownloadButton > button {{
    background-color: var(--mf-panel);
    color: var(--mf-text);
    border: 1px solid var(--mf-border);
    border-radius: 6px;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
  }}
  .stButton > button:hover, .stDownloadButton > button:hover {{
    border-color: var(--mf-cyan);
    box-shadow: 0 0 12px rgba(45, 212, 232, 0.25);
    color: var(--mf-cyan);
  }}
  .stButton > button:focus-visible {{
    outline: 2px solid var(--mf-cyan);
    outline-offset: 2px;
  }}

  [data-testid="stMetric"] {{
    background-color: var(--mf-panel);
    border: 1px solid var(--mf-border);
    border-radius: 8px;
    padding: 0.75rem 1rem;
  }}

  [data-testid="stExpander"] {{
    background-color: var(--mf-panel);
    border: 1px solid var(--mf-border) !important;
    border-radius: 8px;
  }}

  [data-testid="stTabs"] button {{
    color: var(--mf-muted);
  }}
  [data-testid="stTabs"] button[aria-selected="true"] {{
    color: var(--mf-cyan);
  }}

  [data-testid="stDataFrame"] {{
    border: 1px solid var(--mf-border);
    border-radius: 8px;
  }}

  /* -- reusable panel/card primitives for our own HTML blocks -- */
  .mf-panel {{
    background: linear-gradient(180deg, rgba(255,255,255,0.02), transparent),
                var(--mf-panel);
    border: 1px solid var(--mf-border);
    border-radius: 10px;
    padding: 1.1rem 1.3rem;
  }}
  .mf-grid-bg {{
    background-image:
      linear-gradient(var(--mf-grid) 1px, transparent 1px),
      linear-gradient(90deg, var(--mf-grid) 1px, transparent 1px);
    background-size: 32px 32px;
  }}

  /* -- honest status pills: label ALWAYS carries the word, never color-only -- */
  .mf-status {{
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    padding: 0.18rem 0.6rem;
    border-radius: 999px;
    border: 1px solid var(--mf-border);
    text-transform: uppercase;
  }}
  .mf-status-dot {{
    width: 8px; height: 8px; border-radius: 50%;
    display: inline-block;
  }}
  .mf-status--pass {{ color: var(--mf-teal); border-color: var(--mf-teal); }}
  .mf-status--pass .mf-status-dot {{ background: var(--mf-teal); box-shadow: 0 0 8px var(--mf-teal); }}
  .mf-status--warn, .mf-status--inconclusive {{ color: var(--mf-amber); border-color: var(--mf-amber); }}
  .mf-status--warn .mf-status-dot, .mf-status--inconclusive .mf-status-dot {{
    background: var(--mf-amber); box-shadow: 0 0 8px var(--mf-amber);
  }}
  .mf-status--fail {{ color: var(--mf-red); border-color: var(--mf-red); }}
  .mf-status--fail .mf-status-dot {{ background: var(--mf-red); box-shadow: 0 0 8px var(--mf-red); }}
  .mf-status--idle, .mf-status--unavailable {{ color: var(--mf-muted); border-color: var(--mf-border); }}
  .mf-status--idle .mf-status-dot, .mf-status--unavailable .mf-status-dot {{ background: var(--mf-muted); }}

  @media (prefers-reduced-motion: reduce) {{
    * {{ animation-duration: 0.001ms !important; animation-iteration-count: 1 !important;
         transition-duration: 0.001ms !important; }}
  }}
</style>
"""


def inject_base_theme() -> None:
    """Inject the shared dark theme once per script run."""
    st.markdown(BASE_CSS, unsafe_allow_html=True)


def status_class(status: str) -> str:
    """Map an honest backend status word to its CSS status modifier class."""
    key = status.strip().upper()
    mapping = {
        "PASS": "pass",
        "SUCCESS": "pass",
        "VERIFIED": "pass",
        "COMPLETE": "pass",
        "WARN": "warn",
        "WARNING": "warn",
        "INCONCLUSIVE": "inconclusive",
        "FAIL": "fail",
        "FAILURE": "fail",
        "ERROR": "fail",
        "IDLE": "idle",
        "NOT_RUN": "idle",
        "NOT RUN": "idle",
        "UNAVAILABLE": "unavailable",
    }
    return mapping.get(key, "idle")


def status_pill(label: str, status: str) -> str:
    """Render one honest status pill. ``label`` is the word shown -- color
    is never the only signal (accessibility, and the "never fake green"
    rule: the word must always match the color)."""
    cls = status_class(status)
    return (
        f'<span class="mf-status mf-status--{cls}">'
        f'<span class="mf-status-dot"></span>{label}</span>'
    )
