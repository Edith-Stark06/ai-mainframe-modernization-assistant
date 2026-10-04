"""
Entry screen.

Purpose:
    The step between the landing page and the workspace: ask for a name so the
    workspace can greet the engineer.

Responsibilities:
    - :func:`render_entry` -- draw the screen and report the chosen name.

Non-responsibilities:
    - Authentication. No authentication backend exists in this repository, so
      this screen is explicitly and visibly a local, session-only entry point:
      the name (or "Guest") lives only in ``st.session_state`` for the current
      browser session. It never claims to authenticate anyone, and the
      password field is labelled as not verified.

Dependencies:
    - streamlit, app.frontend.design.ui

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from typing import Callable

import streamlit as st

from app.frontend.design import ui

__all__ = ["render_entry"]


def render_entry(*, on_continue: Callable[[str], None]) -> None:
    """Draw the entry screen; call *on_continue* with the chosen name."""
    _, middle, _ = st.columns([1, 1.4, 1])
    with middle:
        ui.render(
            '<div class="ds-entry">'
            + ui.brand_mark(44)
            + '<h1 class="ds-entry-title">Welcome back</h1>'
            '<p class="ds-entry-sub">Sign in to open your workspaces.</p></div>'
        )
        with st.container(border=True, key="entry_card"):
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
                "Sign in", key="entry_sign_in", type="primary", width="stretch"
            ):
                on_continue(name.strip() or "Guest")
            if st.button("Continue as Guest", key="entry_guest", width="stretch"):
                on_continue("Guest")
        ui.render(
            ui.callout(
                "info",
                "A local session, not an account",
                "This is a local, session-only entry point: no account is created and no "
                "credentials are verified against an authentication service. Your name only "
                "personalises this workspace; it does not secure it.",
            )
        )
