"""
Phase 12 — honest "not yet available" rendering.

Per the Phase 12 STEP 0 audit, no API route exists yet for Java
architecture generation, compilation, behavioral validation, or the
Phase 11 quality loop, even though that backend code is fully built
and tested. Rather than fabricate these screens with invented data,
each renders this same honest, still-premium degraded state -- styled
consistently with the rest of the workspace, never a blank page or a
broken widget.
"""

from __future__ import annotations

import streamlit as st

from app.frontend.theme import status_pill

__all__ = ["render_not_yet_available"]


def render_not_yet_available(title: str, reason: str, *, available_today: str) -> None:
    st.markdown(
        f"""
        <div class="mf-panel" style="text-align:center; padding:2.2rem 1.5rem;">
          <div class="mf-muted" style="font-size:0.75rem;letter-spacing:0.1em;">
            {title.upper()}
          </div>
          <div style="margin: 0.6rem 0 0.4rem 0;">{status_pill("NOT AVAILABLE", "UNAVAILABLE")}</div>
          <div class="mf-muted" style="font-size:0.9rem; max-width:32rem; margin:0.6rem auto;">
            {reason}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"Available today: {available_today}")
