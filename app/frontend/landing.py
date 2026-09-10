"""
Phase 12 — the logged-out landing experience.

Composition follows the approved design reference: a quiet top nav, a
two-column hero (copy + CTA on the left, the mainframe -> AI Core ->
modern-architecture diagram on the right), and three restrained
Understand / Transform / Validate cards below. The diagram here always
renders in ``mode="concept"`` (see ``mainframe.py``) -- it illustrates
the product idea, not a specific analyzed program, since no workspace
exists yet at this point in the flow.
"""

from __future__ import annotations

from typing import Callable

import streamlit as st

from app.frontend.mainframe import ChipState, render_mainframe_diagram

__all__ = ["render_landing"]

_HERO_CSS = """
<style>
  .mf-navbar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 0.6rem 0 1.4rem 0; border-bottom: 1px solid var(--mf-border);
    margin-bottom: 1.6rem;
  }
  .mf-brand { font-weight: 700; letter-spacing: 0.06em; font-size: 1.05rem; }
  .mf-brand .mf-tagline { display:block; font-size: 0.65rem; color: var(--mf-muted);
    letter-spacing: 0.12em; font-weight: 500; }
  .mf-navlinks a { color: var(--mf-muted); text-decoration: none; margin-right: 1.4rem;
    font-size: 0.85rem; }
  .mf-navlinks a:hover { color: var(--mf-cyan); }

  .mf-eyebrow { color: var(--mf-cyan); font-size: 0.78rem; letter-spacing: 0.12em;
    font-weight: 600; margin-bottom: 0.6rem; }
  .mf-hero-title { font-size: 2.6rem; line-height: 1.08; font-weight: 800; margin: 0 0 1rem 0; }
  .mf-hero-title .mf-accent { color: var(--mf-cyan); }
  .mf-hero-sub { color: var(--mf-muted); font-size: 1.02rem; max-width: 34rem;
    margin-bottom: 1.6rem; }

  .mf-pillar { border: 1px solid var(--mf-border); border-radius: 10px;
    padding: 1.1rem 1.2rem; background: var(--mf-panel); height: 100%;
    transition: border-color 0.2s ease, transform 0.2s ease; }
  .mf-pillar:hover { border-color: var(--mf-cyan); transform: translateY(-2px); }
  .mf-pillar-title { font-weight: 700; letter-spacing: 0.04em; margin-bottom: 0.4rem;
    color: var(--mf-cyan); font-size: 0.85rem; }
  .mf-pillar-body { color: var(--mf-muted); font-size: 0.88rem; }

  .mf-quote { text-align: center; color: var(--mf-muted); font-style: italic;
    padding: 2rem 0 0.5rem 0; font-size: 0.95rem; }
</style>
"""


def _navbar() -> None:
    st.markdown(
        """
        <div class="mf-navbar">
          <div class="mf-brand">◈ MAINFRAME AI
            <span class="mf-tagline">UNDERSTAND. TRANSFORM. VALIDATE.</span>
          </div>
          <div class="mf-navlinks">
            <a href="#understand">Product</a>
            <a href="#understand">How it Works</a>
            <a href="#transform">Use Cases</a>
            <a href="#validate">About</a>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_landing(
    *,
    on_enter_platform: Callable[[], None],
    on_login: Callable[[], None],
    on_watch_intro: Callable[[], None],
    intro_seen: bool,
) -> None:
    st.markdown(_HERO_CSS, unsafe_allow_html=True)
    _navbar()

    top_l, top_r = st.columns([5, 1])
    with top_r:
        if st.button("Login", key="landing_login_link", use_container_width=True):
            on_login()

    hero_l, hero_r = st.columns([1, 1], gap="large")
    with hero_l:
        st.markdown(
            """
            <div class="mf-eyebrow">LEGACY SYSTEMS → MODERN POSSIBILITIES</div>
            <div class="mf-hero-title">AI-ASSISTED<br/>MAINFRAME<br/>
              <span class="mf-accent">MODERNIZATION</span></div>
            <div class="mf-hero-sub">From complex COBOL systems to evidence-backed
              modern architecture. Every result you see is grounded in real
              analysis — nothing is fabricated for the sake of a demo.</div>
            """,
            unsafe_allow_html=True,
        )
        btn_l, btn_r = st.columns([1, 1])
        with btn_l:
            if st.button(
                "Enter the Platform →",
                key="landing_enter_platform",
                type="primary",
                use_container_width=True,
            ):
                on_enter_platform()
        with btn_r:
            label = "Watch Intro" if not intro_seen else "Replay Intro"
            if st.button(label, key="landing_watch_intro", use_container_width=True):
                on_watch_intro()

    with hero_r:
        render_mainframe_diagram(
            ChipState.ANALYSIS_COMPLETE,
            mode="concept",
            play_boot=not intro_seen,
        )
        if not intro_seen:
            st.caption("First visit — playing the boot sequence once.")
            if st.button("Skip Intro", key="landing_skip_intro"):
                on_watch_intro()  # caller marks intro_seen; same handler either way

    st.markdown("<div id='understand'></div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3, gap="medium")
    with c1:
        st.markdown(
            '<div class="mf-pillar"><div class="mf-pillar-title">UNDERSTAND</div>'
            '<div class="mf-pillar-body">AI-assisted analysis of programs, data, '
            "logic, dependencies, and business rules — deterministic, "
            "evidence-based, never a guess dressed up as a fact.</div></div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            '<div id="transform"></div>'
            '<div class="mf-pillar"><div class="mf-pillar-title">TRANSFORM</div>'
            '<div class="mf-pillar-body">Generate maintainable modern Java '
            "architecture with full traceability back to its COBOL source.</div></div>",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            '<div id="validate"></div>'
            '<div class="mf-pillar"><div class="mf-pillar-title">VALIDATE</div>'
            '<div class="mf-pillar-body">Compilation, testing, and behavioral '
            "validation for confidence — reported honestly, including when the "
            "answer is INCONCLUSIVE.</div></div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="mf-quote">"Modernization isn\'t just about new code. '
        "It's about preserving what works and unlocking what's next.\"</div>",
        unsafe_allow_html=True,
    )
