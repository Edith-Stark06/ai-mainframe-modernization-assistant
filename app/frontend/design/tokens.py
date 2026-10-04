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

Look:
    Deep navy surfaces with a cyan accent in the dark theme (the platform's
    original look) and a cool blue-grey surface with a deeper cyan-blue accent
    in the light theme. Text, status colors and non-text marks are chosen so
    every pair in :data:`TEXT_PAIRS` / :data:`MARK_PAIRS` meets WCAG 2.1 AA in
    both palettes. :attr:`Palette.brand` is for non-text marks (brand mark,
    accents) where 3:1 is the requirement; :attr:`Palette.primary` carries
    buttons and links.

Dependencies:
    - none (standard library only)

Examples:
    >>> round(contrast_ratio("#000000", "#ffffff"), 1)
    21.0

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
    brand: str  # decorative accent (non-text marks only)
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
    canvas="#f5f8fb",
    surface="#ffffff",
    surface_soft="#eaf0f6",
    surface_strong="#dce6f0",
    hairline="#d5dfe9",
    hairline_strong="#6f8396",
    ink="#0b1620",
    body="#2b3a49",
    muted="#4b5d6f",
    brand="#0b8aa3",
    primary="#0a6c86",
    primary_hover="#085870",
    on_primary="#ffffff",
    primary_tint="#d9eef4",
    primary_text="#085870",
    success="#2f6f44",
    success_bg="#e3f1e8",
    warning="#7a5600",
    warning_bg="#f7ecce",
    error="#a63232",
    error_bg="#f7e2df",
    info="#2b5fb3",
    info_bg="#e1eaf8",
    neutral="#4a5866",
    neutral_bg="#e4ebf2",
    success_mark="#2f9a62",
    warning_mark="#b27b00",
    error_mark="#c64545",
    info_mark="#3f7bd1",
    neutral_mark="#6f8396",
    code_bg="#0d1117",
    code_fg="#e6edf3",
    code_muted="#8b98a5",
    grid="#dfe8f1",
    focus="#0a6c86",
)

DARK = Palette(
    name="dark",
    canvas="#080c12",
    surface="#0d1117",
    surface_soft="#0a0e14",
    surface_strong="#16212d",
    hairline="#1c2733",
    hairline_strong="#6b7f93",
    ink="#e6edf3",
    body="#c3ced8",
    muted="#93a1af",
    brand="#2dd4e8",
    primary="#2dd4e8",
    primary_hover="#5ce3f2",
    on_primary="#04161a",
    primary_tint="#0f2c36",
    primary_text="#5ce3f2",
    success="#3ddc97",
    success_bg="#0f2b21",
    warning="#e8a92d",
    warning_bg="#33260c",
    error="#f27c7c",
    error_bg="#3a1618",
    info="#7db4f5",
    info_bg="#12263f",
    neutral="#b0bcc8",
    neutral_bg="#1a2531",
    success_mark="#3ddc97",
    warning_mark="#e8a92d",
    error_mark="#e84d4d",
    info_mark="#5b9bf0",
    neutral_mark="#7b8794",
    code_bg="#05070a",
    code_fg="#e6edf3",
    code_muted="#8b98a5",
    grid="#1c2733",
    focus="#2dd4e8",
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
