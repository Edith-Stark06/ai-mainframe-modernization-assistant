"""
Theme entry points for the workspace UI.

Purpose:
    The stable import surface views use to apply the dashboard theme and render
    a status. The look itself lives in :mod:`app.frontend.design` (tokens,
    stylesheet, UI primitives); this module only forwards to it so view code
    does not depend on how the design system is organised.

Responsibilities:
    - :func:`inject_base_theme` -- inject the stylesheet for the active
      light / dark theme.
    - :func:`status_pill` / :func:`status_class` -- render / classify an honest
      backend status word (icon + word, never color alone).

Non-responsibilities:
    - Any color, font or layout decision (see :mod:`app.frontend.design`).

Dependencies:
    - app.frontend.design.styles, app.frontend.design.ui

Examples:
    >>> "ds-badge--success" in status_pill("Pass", "PASS")
    True

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from app.frontend.design import styles, ui

__all__ = ["inject_base_theme", "status_class", "status_pill"]

#: tone -> the legacy ``mf-status--*`` modifier older code and tests refer to.
_LEGACY_CLASS = {
    "success": "pass",
    "warning": "inconclusive",
    "error": "fail",
    "info": "idle",
    "neutral": "idle",
}


def inject_base_theme(*, extra: tuple[str, ...] = ()) -> None:
    """Inject the dashboard stylesheet (light or dark, as the session uses).

    Args:
        extra: Additional stylesheet names to append, for example
            ``("chat.css",)`` for the assistant view.
    """
    styles.inject(extra=extra)


def status_class(status: str) -> str:
    """Map an honest backend status word to its legacy CSS modifier."""
    key = status.strip().upper()
    if key in ("WARN", "WARNING"):
        return "warn"
    return _LEGACY_CLASS[ui.tone_for(key)]


def status_pill(label: str, status: str) -> str:
    """One honest status badge.

    ``label`` is the word shown; the icon and tone come from ``status``. Color
    is never the only signal, and the word must always match the tone (the
    "never fake green" rule).
    """
    tone = ui.tone_for(status)
    glyph = {"success": "check", "warning": "alert", "error": "x", "info": "info"}.get(
        tone, "minus"
    )
    return ui.badge(label, tone, glyph)
