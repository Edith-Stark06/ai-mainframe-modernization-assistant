"""
Design tokens.

Purpose:
    The single source of truth for the dashboard's colors, type, spacing,
    radii and elevation, in a light and a dark palette. Every CSS value and
    every Streamlit theme option is derived from here; nothing else in the
    frontend hard-codes a color.

Responsibilities:
    - :class:`Palette` and the two instances :data:`LIGHT` / :data:`DARK`.
    - :func:`contrast_ratio` (WCAG 2.1 relative luminance), so the palettes are
      *tested* against the accessibility thresholds instead of trusted
      (``tests/frontend/test_design_tokens.py``).
    - :data:`TEXT_PAIRS` / :data:`MARK_PAIRS` -- which foreground/background
      combinations must pass, and by how much.

Non-responsibilities:
    - Building CSS (see :mod:`app.frontend.design.styles`) or markup
      (see :mod:`app.frontend.design.ui`).

Provenance:
    The look follows ``DESIGN.md`` at the repository root (warm cream canvas,
    coral accent, serif display, dark product surfaces). Where that document's
    values fail WCAG 2.1 AA they are adjusted, never used as-is:

    ============================  ==========  ==========  ===============
    Use                           DESIGN.md   Here        Why
    ============================  ==========  ==========  ===============
    Button fill (white text)      #cc785c     #a9583e     3.28 -> 5.06:1
    Coral as link / text          #cc785c     #a9583e     3.11 -> 4.80:1
    Secondary text on cards       #6c6a64     #66645e     4.48 -> 4.90:1
    Success / warning / error     #5db872 ..  darker      2.3  -> >=5:1
    Input borders                 #e6dfd8     #8e8b82     1.25 -> 3.23:1
    ============================  ==========  ==========  ===============

    The original coral (:attr:`Palette.brand`) is kept for non-text marks
    (brand mark, accents) where 3:1 is the requirement.

Dependencies:
    - none (standard library only)

Examples:
    >>> round(contrast_ratio("#141413", "#faf9f5"), 1)
    17.5

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

__all__ = [
    "DARK",
    "FONT_CODE",
    "FONT_DISPLAY",
    "FONT_SANS",
    "LIGHT",
    "MARK_PAIRS",
    "Palette",
    "RADIUS",
    "SPACE",
    "TEXT_PAIRS",
    "contrast_ratio",
    "palette_for",
]

# ----------------------------------------------------------------------------
# Type
# ----------------------------------------------------------------------------

#: Bundled, OFL-licensed variable fonts (app/frontend/static/fonts); no
#: third-party request is made at runtime. The fallbacks are what renders if a
#: font file is blocked.
FONT_SANS = (
    '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, '
    '"Helvetica Neue", Arial, sans-serif'
)
FONT_DISPLAY = '"Source Serif 4", "Tiempos Headline", Georgia, "Times New Roman", serif'
FONT_CODE = (
    '"JetBrains Mono", ui-monospace, "SF Mono", Menlo, Consolas, '
    '"Liberation Mono", monospace'
)

# ----------------------------------------------------------------------------
# Scales (4px base)
# ----------------------------------------------------------------------------

SPACE = {
    "xxs": "4px",
    "xs": "8px",
    "sm": "12px",
    "md": "16px",
    "lg": "24px",
    "xl": "32px",
    "xxl": "48px",
}

RADIUS = {
    "xs": "4px",
    "sm": "6px",
    "md": "8px",
    "lg": "12px",
    "xl": "16px",
    "pill": "999px",
}


@dataclass(frozen=True)
class Palette:
    """One complete color set. Field names are the CSS custom-property names
    (``canvas`` -> ``--c-canvas``)."""

    name: str

    # surfaces
    canvas: str  # page floor
    surface: str  # cards
    surface_soft: str  # sidebar, inset areas, table headers
    surface_strong: str  # selected / hovered rows, active tabs
    hairline: str  # decorative borders (exempt from 3:1)
    hairline_strong: str  # control borders (must reach 3:1)

    # text
    ink: str  # headings, primary text
    body: str  # running text
    muted: str  # secondary text (still >= 4.5:1 on every surface)

    # brand / primary action
    brand: str  # decorative coral (non-text marks only)
    primary: str  # button fill, links, active indicator
    primary_hover: str
    on_primary: str  # text on the primary fill
    primary_tint: str  # selected-nav / callout background
    primary_text: str  # accent text on tinted backgrounds

    # status text colors (>= 4.5:1 on canvas, surface and their own tint)
    success: str
    success_bg: str
    warning: str
    warning_bg: str
    error: str
    error_bg: str
    info: str
    info_bg: str
    neutral: str
    neutral_bg: str

    # status marks: dots, bars, meters (>= 3:1 against canvas and surface)
    success_mark: str
    warning_mark: str
    error_mark: str
    info_mark: str
    neutral_mark: str

    # product / code surfaces: always dark, in both themes (as in DESIGN.md)
    code_bg: str
    code_fg: str
    code_muted: str

    # chart ink
    grid: str  # gridlines, axes: one step off the surface

    focus: str  # focus ring


LIGHT = Palette(
    name="light",
    canvas="#faf9f5",
    surface="#ffffff",
    surface_soft="#f5f0e8",
    surface_strong="#efe9de",
    hairline="#e6dfd8",
    hairline_strong="#8e8b82",
    ink="#141413",
    body="#3d3d3a",
    muted="#66645e",
    brand="#cc785c",
    primary="#a9583e",
    primary_hover="#8f4630",
    on_primary="#ffffff",
    primary_tint="#f3e3da",
    primary_text="#8f4630",
    success="#2f6f44",
    success_bg="#e5f1e7",
    warning="#7a5600",
    warning_bg="#f7ecce",
    error="#a63232",
    error_bg="#f7e2df",
    info="#2c6a8f",
    info_bg="#e1edf4",
    neutral="#5f5d57",
    neutral_bg="#ece7de",
    success_mark="#3b8a57",
    warning_mark="#b27b00",
    error_mark="#c64545",
    info_mark="#3a7ca5",
    neutral_mark="#8e8b82",
    code_bg="#181715",
    code_fg="#faf9f5",
    code_muted="#a09d96",
    grid="#ebe6df",
    focus="#a9583e",
)

DARK = Palette(
    name="dark",
    canvas="#181715",
    surface="#1f1e1b",
    surface_soft="#141311",
    surface_strong="#2c2a26",
    hairline="#34312c",
    hairline_strong="#8e8b82",
    ink="#faf9f5",
    body="#e3e0d8",
    muted="#a09d96",
    brand="#cc785c",
    primary="#e08a6d",
    primary_hover="#eba086",
    on_primary="#181715",
    primary_tint="#3a2a23",
    primary_text="#eba086",
    success="#6fcf8c",
    success_bg="#1f3326",
    warning="#e8b04a",
    warning_bg="#3a2f17",
    error="#ee7a72",
    error_bg="#40201e",
    info="#6cb2dd",
    info_bg="#1c3140",
    neutral="#b8b5ad",
    neutral_bg="#2c2a26",
    success_mark="#5bbd7a",
    warning_mark="#d9a037",
    error_mark="#e0675f",
    info_mark="#5aa3cf",
    neutral_mark="#8e8b82",
    code_bg="#0f0e0d",
    code_fg="#faf9f5",
    code_muted="#a09d96",
    grid="#2c2a26",
    focus="#e08a6d",
)


def palette_for(theme: str | None) -> Palette:
    """The palette for a Streamlit theme type (``"light"`` / ``"dark"``).

    Anything else (including ``None``, which an unthemed test context or an
    older client reports) is the light palette.
    """
    return DARK if (theme or "").lower() == "dark" else LIGHT


# ----------------------------------------------------------------------------
# Contrast (WCAG 2.1)
# ----------------------------------------------------------------------------


def _channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(color: str) -> float:
    h = color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 2.1 contrast ratio between two ``#rrggbb`` colors (1.0 .. 21.0)."""
    a, b = _luminance(foreground), _luminance(background)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


#: ``(foreground field, background field)`` pairs that carry *text* and must
#: reach 4.5:1 (WCAG 1.4.3) in both palettes.
TEXT_PAIRS: tuple[tuple[str, str], ...] = (
    ("ink", "canvas"),
    ("ink", "surface"),
    ("ink", "surface_soft"),
    ("ink", "surface_strong"),
    ("body", "canvas"),
    ("body", "surface"),
    ("body", "surface_soft"),
    ("body", "surface_strong"),
    ("muted", "canvas"),
    ("muted", "surface"),
    ("muted", "surface_soft"),
    ("muted", "surface_strong"),
    ("on_primary", "primary"),
    ("on_primary", "primary_hover"),
    ("primary", "canvas"),
    ("primary", "surface"),
    ("primary_text", "primary_tint"),
    ("primary_text", "canvas"),
    ("success", "canvas"),
    ("success", "surface"),
    ("success", "success_bg"),
    ("warning", "canvas"),
    ("warning", "surface"),
    ("warning", "warning_bg"),
    ("error", "canvas"),
    ("error", "surface"),
    ("error", "error_bg"),
    ("info", "canvas"),
    ("info", "surface"),
    ("info", "info_bg"),
    ("neutral", "canvas"),
    ("neutral", "surface"),
    ("neutral", "neutral_bg"),
    ("code_fg", "code_bg"),
    ("code_muted", "code_bg"),
)

#: Pairs that carry *meaning without text* (status dots, bars, meter fills,
#: control borders, focus rings) and must reach 3:1 (WCAG 1.4.11).
MARK_PAIRS: tuple[tuple[str, str], ...] = (
    ("success_mark", "canvas"),
    ("success_mark", "surface"),
    ("warning_mark", "canvas"),
    ("warning_mark", "surface"),
    ("error_mark", "canvas"),
    ("error_mark", "surface"),
    ("info_mark", "canvas"),
    ("info_mark", "surface"),
    ("neutral_mark", "canvas"),
    ("neutral_mark", "surface"),
    ("hairline_strong", "canvas"),
    ("hairline_strong", "surface"),
    ("focus", "canvas"),
    ("focus", "surface"),
    ("brand", "canvas"),
)


def as_dict(palette: Palette) -> dict[str, str]:
    """The palette as ``{field: value}``, without its name."""
    data = asdict(palette)
    data.pop("name")
    return data
