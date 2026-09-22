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
import streamlit.components.v1 as components

from app.frontend.landing_template import LANDING_HTML, Z17_IMAGE_B64

__all__ = ["render_landing"]


def render_landing(
    *,
    on_enter_platform: Callable[[], None],
    on_login: Callable[[], None],
    on_watch_intro: Callable[[], None],
    intro_seen: bool,
) -> None:
    # Inject the base64 encoded z17 image
    html_content = LANDING_HTML.replace("{Z17_IMAGE_B64}", Z17_IMAGE_B64)

    # Set a large height to ensure Streamlit renders it properly, the iframe JS will resize it.
    components.html(html_content, height=10000, scrolling=True)

    # Render hidden Streamlit buttons that the JS bridge will click
    # Since the overlay has z-index: 999999, these will be hidden underneath it.
    if st.button("Login", key="landing_login_link"):
        on_login()

    if st.button("Get Started →", key="landing_enter_platform"):
        on_enter_platform()

    if st.button("Watch Demo", key="landing_watch_intro"):
        on_watch_intro()
