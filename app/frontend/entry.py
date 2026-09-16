"""
Phase 12 — entry/login screen.

No real authentication backend exists anywhere in this repository
(verified during the Phase 12 STEP 0 audit). Rather than fabricate a
production-looking sign-in, this screen is explicitly and visibly a
local, session-only entry point: whatever name is entered (or "Guest")
is stored only in ``st.session_state`` for the current browser session,
purely to personalize the workspace greeting. It never claims to
authenticate anyone.
"""

from __future__ import annotations

from typing import Callable

import streamlit as st

__all__ = ["render_entry"]

_ENTRY_CSS = """
<style>
  .mf-entry-wrap { max-width: 26rem; margin: 3rem auto 0 auto; text-align: center; }
  .mf-entry-badge { font-size: 1.6rem; margin-bottom: 0.4rem; }
  .mf-entry-title { font-weight: 700; letter-spacing: 0.08em; font-size: 1.1rem;
    margin-bottom: 1.6rem; color: var(--mf-text); }
  .mf-entry-note { font-size: 0.76rem; color: var(--mf-muted); margin-top: 1rem;
    border-top: 1px solid var(--mf-border); padding-top: 0.8rem; }
</style>
"""


def render_entry(*, on_continue: Callable[[str], None]) -> None:
    st.markdown(_ENTRY_CSS, unsafe_allow_html=True)
    st.markdown(
        """
        <div class="mf-entry-wrap">
          <div class="mf-entry-badge">◈</div>
          <div class="mf-entry-title">WELCOME BACK, ENGINEER</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        name = st.text_input(
            "Engineer name (optional)",
            value="",
            key="entry_name",
            placeholder="e.g. Alex",
        )
        st.text_input(
            "Password (demo session — not verified)",
            value="",
            type="password",
            key="entry_password",
        )
        if st.button(
            "Sign In", key="entry_sign_in", type="primary", use_container_width=True
        ):
            on_continue(name.strip() or "Guest")
        if st.button("Continue as Guest", key="entry_guest", use_container_width=True):
            on_continue("Guest")

        st.markdown(
            '<div class="mf-entry-note">This is a local, session-only entry point — '
            "no account is created and no credentials are verified against a real "
            "authentication service. It exists to personalize the workspace, not to "
            "secure it.</div>",
            unsafe_allow_html=True,
        )
