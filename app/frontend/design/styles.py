"""
Stylesheet assembly.

Purpose:
    Builds the CSS the dashboard injects: a ``:root`` block of custom properties
    for the active theme (from :mod:`app.frontend.design.tokens`), the bundled
    font faces, and the static component stylesheet (``dashboard.css``).

Responsibilities:
    - :func:`root_block` -- the ``:root { --c-... }`` custom properties.
    - :func:`font_faces` -- ``@font-face`` rules for the bundled fonts.
    - :func:`build_css` -- everything above plus ``dashboard.css``.
    - :func:`active_theme` -- ``"light"`` / ``"dark"`` from the running Streamlit
      session, falling back to light.
    - :func:`inject` -- write the CSS into the page (once per script run).

Non-responsibilities:
    - Component markup (see :mod:`app.frontend.design.ui`).

Dependencies:
    - streamlit (only in :func:`active_theme` / :func:`inject`)
    - app.frontend.design.tokens

Examples:
    >>> ":root" in build_css("light")
    True

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.frontend.design.tokens import (
    FONT_CODE,
    FONT_DISPLAY,
    FONT_SANS,
    RADIUS,
    SPACE,
    Palette,
    as_dict,
    palette_for,
)

__all__ = [
    "active_theme",
    "build_css",
    "font_faces",
    "inject",
    "load_css",
    "root_block",
]

_CSS_DIR = Path(__file__).parent

#: Where Streamlit serves ``app/frontend/static`` (see ``enableStaticServing``).
_FONT_URL = "app/static/fonts"

_FONTS = (
    ("Inter", "Inter-Variable.woff2", "100 900"),
    ("Source Serif 4", "SourceSerif4-Variable.woff2", "200 900"),
    ("JetBrains Mono", "JetBrainsMono-Variable.woff2", "100 800"),
)


def _css_name(field: str) -> str:
    return field.replace("_", "-")


def root_block(palette: Palette) -> str:
    """The ``:root`` block defining every token as a CSS custom property."""
    lines = [f"--c-{_css_name(k)}: {v};" for k, v in as_dict(palette).items()]
    lines += [f"--r-{k}: {v};" for k, v in RADIUS.items()]
    lines += [f"--s-{k}: {v};" for k, v in SPACE.items()]
    lines += [
        f"--font-sans: {FONT_SANS};",
        f"--font-display: {FONT_DISPLAY};",
        f"--font-code: {FONT_CODE};",
    ]
    if palette.name == "dark":
        lines += [
            "--shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.35);",
            "--shadow-pop: 0 12px 32px rgba(0, 0, 0, 0.55);",
            "color-scheme: dark;",
        ]
    else:
        lines += [
            "--shadow-sm: 0 1px 2px rgba(20, 20, 19, 0.04);",
            "--shadow-pop: 0 10px 30px rgba(20, 20, 19, 0.12);",
            "color-scheme: light;",
        ]
    return ":root {\n  " + "\n  ".join(lines) + "\n}"


def font_faces() -> str:
    """``@font-face`` rules for the bundled variable fonts."""
    return "\n".join(
        f"@font-face {{ font-family: '{family}'; src: url('{_FONT_URL}/{file}') "
        f"format('woff2'); font-weight: {weight}; font-style: normal; "
        "font-display: swap; }"
        for family, file, weight in _FONTS
    )


@lru_cache(maxsize=None)
def load_css(name: str) -> str:
    """The text of a stylesheet that sits next to this module."""
    return (_CSS_DIR / name).read_text(encoding="utf-8")


def build_css(theme: str | None = "light", *, extra: tuple[str, ...] = ()) -> str:
    """
    The complete stylesheet for *theme*.

    Args:
        theme: ``"light"`` or ``"dark"`` (anything else is light).
        extra: Names of additional stylesheets to append (for example the chat
            view's ``chat.css``).

    Returns:
        ``<style>``-ready CSS text (without the tags).
    """
    parts = [font_faces(), root_block(palette_for(theme)), load_css("dashboard.css")]
    parts += [load_css(name) for name in extra]
    return "\n".join(parts)


def active_theme() -> str:
    """The theme of the running Streamlit session (``"light"`` / ``"dark"``).

    Streamlit reports ``None`` outside a browser session (for example in
    ``AppTest``) and may not provide the API at all in an older version; both
    fall back to light.
    """
    try:
        import streamlit as st

        theme = st.context.theme.type
    except Exception:  # noqa: BLE001 - any failure means "unknown": use light
        return "light"
    return "dark" if theme == "dark" else "light"


def inject(*, extra: tuple[str, ...] = ()) -> None:
    """Write the dashboard CSS into the page for the active theme."""
    import streamlit as st

    st.markdown(
        f"<style>{build_css(active_theme(), extra=extra)}</style>",
        unsafe_allow_html=True,
    )
