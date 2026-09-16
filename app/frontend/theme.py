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
# amber for genuine warnings, red only for genuine failure. Violet is
# reserved exclusively for the AI surface (Modernization Chat, the "AI"
# sidebar group) -- never used as a status color, so it never competes
# with the honest PASS/INCONCLUSIVE/FAIL/NOT AVAILABLE palette below.
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
VIOLET = "#9b87e8"

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
    --mf-violet: {VIOLET};
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
    box-shadow: 0 0 4px rgba(45, 212, 232, 0.15);
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
  .mf-status--pass .mf-status-dot {{ background: var(--mf-teal); box-shadow: 0 0 3px var(--mf-teal); }}
  .mf-status--warn, .mf-status--inconclusive {{ color: var(--mf-amber); border-color: var(--mf-amber); }}
  .mf-status--warn .mf-status-dot, .mf-status--inconclusive .mf-status-dot {{
    background: var(--mf-amber); box-shadow: 0 0 3px var(--mf-amber);
  }}
  .mf-status--fail {{ color: var(--mf-red); border-color: var(--mf-red); }}
  .mf-status--fail .mf-status-dot {{ background: var(--mf-red); box-shadow: 0 0 3px var(--mf-red); }}
  .mf-status--idle, .mf-status--unavailable {{ color: var(--mf-muted); border-color: var(--mf-border); }}
  .mf-status--idle .mf-status-dot, .mf-status--unavailable .mf-status-dot {{ background: var(--mf-muted); }}

  @media (prefers-reduced-motion: reduce) {{
    * {{ animation-duration: 0.001ms !important; animation-iteration-count: 1 !important;
         transition-duration: 0.001ms !important; }}
  }}

  /* -- Stitch-locked layout primitives (compact, dense, restrained glow) -- */

  /* sidebar nav: quiet by default; the active item is a real st.button
     with type="primary", restyled here into a left-accent row instead of
     Streamlit's default filled-blue button */
  [data-testid="stSidebar"] .stButton {{ width: 100%; }}
  [data-testid="stSidebar"] .stButton > button {{
    width: 100%;
    display: flex;
    text-align: left;
    justify-content: flex-start;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    box-shadow: none;
    font-size: 0.85rem;
    padding: 0.35rem 0.6rem;
  }}
  [data-testid="stSidebar"] .stButton > button > div {{
    width: 100%;
    justify-content: flex-start;
  }}
  [data-testid="stSidebar"] .stButton > button:hover {{
    border-color: transparent;
    box-shadow: none;
    background: rgba(45, 212, 232, 0.06);
    color: var(--mf-text);
  }}
  [data-testid="stSidebar"] .stButton > button[kind="primary"] {{
    background: rgba(45, 212, 232, 0.09);
    border-left: 2px solid var(--mf-cyan);
    border-radius: 4px;
    color: var(--mf-cyan);
    font-weight: 600;
  }}
  [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {{
    background: rgba(45, 212, 232, 0.12);
  }}
  .mf-nav-group {{
    margin: 0.9rem 0 0.15rem 0.6rem;
    font-size: 0.66rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: var(--mf-muted);
  }}
  /* the AI surface (Modernization Chat) gets the one restrained violet
     accent in the app -- never used for status, so it never collides
     with the PASS/INCONCLUSIVE/FAIL/NOT AVAILABLE palette. */
  .mf-nav-group--ai {{ color: var(--mf-violet); }}
  .mf-ai-accent {{ color: var(--mf-violet) !important; }}
  .mf-ai-border {{ border-color: var(--mf-violet) !important; }}
  .mf-nav-brand {{
    font-weight: 700;
    letter-spacing: 0.06em;
    font-size: 0.95rem;
    padding: 0.2rem 0.4rem 0.8rem 0.4rem;
    border-bottom: 1px solid var(--mf-border);
    margin-bottom: 0.4rem;
  }}
  .mf-nav-brand .mf-tagline {{
    display: block;
    font-size: 0.62rem;
    color: var(--mf-muted);
    letter-spacing: 0.1em;
    font-weight: 500;
  }}

  /* top bar -- split across st.columns (left: file/status, right: Help +
     session) so a real st.popover can sit inline with the HTML info
     block; .mf-topbar-rule draws the shared bottom border beneath both. */
  .mf-topbar-left {{
    display: flex;
    align-items: center;
    padding: 0.5rem 0.1rem;
  }}
  .mf-topbar-file {{ font-weight: 600; font-size: 0.92rem; }}
  .mf-topbar-badge {{
    display: inline-block;
    font-size: 0.66rem;
    letter-spacing: 0.06em;
    color: var(--mf-muted);
    border: 1px solid var(--mf-border);
    border-radius: 4px;
    padding: 0.05rem 0.35rem;
    margin-left: 0.5rem;
  }}
  .mf-topbar-session {{
    font-size: 0.78rem;
    color: var(--mf-muted);
    text-align: right;
    padding: 0.6rem 0.1rem 0.5rem 0;
  }}
  .mf-topbar-rule {{
    border-bottom: 1px solid var(--mf-border);
    margin: -0.5rem 0 1rem 0;
  }}
  [data-testid="stPopoverBody"] {{
    background-color: var(--mf-panel);
    border: 1px solid var(--mf-border);
  }}

  /* section header (Level 1) */
  .mf-section-header {{ margin-bottom: 0.9rem; }}
  .mf-eyebrow-sm {{
    color: var(--mf-cyan); font-size: 0.68rem; letter-spacing: 0.1em;
    font-weight: 600; margin-bottom: 0.2rem; text-transform: uppercase;
  }}
  .mf-section-title {{ font-size: 1.35rem; font-weight: 700; letter-spacing: 0.01em; }}
  .mf-subtitle {{ color: var(--mf-muted); font-size: 0.88rem; margin-top: 0.15rem; }}

  /* stat row (Level 2 metrics) */
  .mf-statrow {{
    display: flex;
    flex-wrap: wrap;
    border: 1px solid var(--mf-border);
    border-radius: 8px;
    background: var(--mf-panel);
    margin-bottom: 1rem;
  }}
  .mf-stat {{
    flex: 1 1 0;
    min-width: 6rem;
    padding: 0.6rem 0.9rem;
    border-right: 1px solid var(--mf-border);
  }}
  .mf-stat:last-child {{ border-right: none; }}
  .mf-stat-value {{ font-size: 1.25rem; font-weight: 700; color: var(--mf-text); }}
  .mf-stat-label {{
    font-size: 0.62rem; letter-spacing: 0.08em; color: var(--mf-muted);
    text-transform: uppercase; margin-top: 0.1rem;
  }}

  /* pipeline stepper */
  .mf-pipeline {{
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.7rem 0.2rem;
    margin-bottom: 1rem;
    flex-wrap: wrap;
  }}
  .mf-step {{
    display: flex; align-items: center; gap: 0.35rem;
    font-size: 0.76rem; letter-spacing: 0.05em; font-weight: 600;
    padding: 0.2rem 0.6rem; border-radius: 999px; border: 1px solid var(--mf-border);
    color: var(--mf-muted);
  }}
  .mf-step--done {{ color: var(--mf-teal); border-color: var(--mf-teal); }}
  .mf-step--active {{ color: var(--mf-cyan); border-color: var(--mf-cyan); }}
  .mf-step--partial {{ color: var(--mf-amber); border-color: var(--mf-amber); }}
  .mf-step--fail {{ color: var(--mf-red); border-color: var(--mf-red); }}
  .mf-step--pending {{ color: var(--mf-muted); }}
  .mf-step-glyph {{ font-size: 0.8rem; }}

  /* status matrix */
  .mf-matrix {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
    gap: 1px;
    background: var(--mf-border);
    border: 1px solid var(--mf-border);
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 1rem;
  }}
  .mf-matrix-cell {{
    background: var(--mf-panel);
    padding: 0.6rem 0.8rem;
    display: flex; flex-direction: column; gap: 0.35rem;
  }}
  .mf-matrix-label {{
    font-size: 0.68rem; letter-spacing: 0.06em; color: var(--mf-muted);
    text-transform: uppercase;
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
