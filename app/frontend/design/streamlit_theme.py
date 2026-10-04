"""
Streamlit theme configuration.

Purpose:
    Streamlit themes its own widgets (inputs, selects, tables, the sidebar,
    badges) from ``.streamlit/config.toml``. Generating that file from the
    design tokens means the native controls and our custom components share one
    palette in both light and dark, instead of fighting each other with CSS.

Responsibilities:
    - :func:`render_config_toml` -- the exact text of ``.streamlit/config.toml``.
    - ``python -m app.frontend.design.streamlit_theme`` prints it (regenerate the
      file with ``... > .streamlit/config.toml``).

Non-responsibilities:
    - Custom components and layout (see :mod:`app.frontend.design.styles`).

Dependencies:
    - app.frontend.design.tokens

Examples:
    ::

        python -m app.frontend.design.streamlit_theme > .streamlit/config.toml

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from app.frontend.design.tokens import DARK, LIGHT, Palette

__all__ = ["render_config_toml"]

_FONT_FACES = (
    ("Inter", "Inter-Variable.woff2", "100 900"),
    ("Source Serif 4", "SourceSerif4-Variable.woff2", "200 900"),
    ("JetBrains Mono", "JetBrainsMono-Variable.woff2", "100 800"),
)

#: Heading scale (h1..h6). The serif display face is used for h1-h3 only.
_HEADING_SIZES = '["2rem", "1.5rem", "1.25rem", "1.0625rem", "1rem", "0.875rem"]'
_HEADING_WEIGHTS = "[500, 500, 500, 600, 600, 600]"


def _theme_block(section: str, p: Palette) -> str:
    """One ``[theme.<section>]`` (and its sidebar) block."""
    # The sidebar is the soft surface; the main page is the canvas.
    return f"""[theme.{section}]
primaryColor = "{p.primary}"
backgroundColor = "{p.canvas}"
secondaryBackgroundColor = "{p.surface_soft}"
textColor = "{p.ink}"
linkColor = "{p.primary_text}"
linkUnderline = true
borderColor = "{p.hairline}"
dataframeBorderColor = "{p.hairline}"
dataframeHeaderBackgroundColor = "{p.surface_soft}"
showWidgetBorder = true
baseRadius = "8px"
buttonRadius = "8px"
codeBackgroundColor = "{p.surface_strong}"
codeTextColor = "{p.ink}"
redColor = "{p.error_mark}"
redTextColor = "{p.error}"
redBackgroundColor = "{p.error_bg}"
orangeColor = "{p.warning_mark}"
orangeTextColor = "{p.warning}"
orangeBackgroundColor = "{p.warning_bg}"
yellowColor = "{p.warning_mark}"
yellowTextColor = "{p.warning}"
yellowBackgroundColor = "{p.warning_bg}"
greenColor = "{p.success_mark}"
greenTextColor = "{p.success}"
greenBackgroundColor = "{p.success_bg}"
blueColor = "{p.info_mark}"
blueTextColor = "{p.info}"
blueBackgroundColor = "{p.info_bg}"
violetColor = "{p.neutral_mark}"
violetTextColor = "{p.neutral}"
violetBackgroundColor = "{p.neutral_bg}"
grayColor = "{p.neutral_mark}"
grayTextColor = "{p.neutral}"
grayBackgroundColor = "{p.neutral_bg}"

[theme.{section}.sidebar]
backgroundColor = "{p.surface_soft}"
secondaryBackgroundColor = "{p.surface_strong}"
borderColor = "{p.hairline}"
"""


def render_config_toml() -> str:
    """The full text of ``.streamlit/config.toml`` (generated -- do not edit)."""
    faces = "\n".join(f"""[[theme.fontFaces]]
family = "{family}"
url = "app/static/fonts/{file}"
weight = "{weight}"
style = "normal"
""" for family, file, weight in _FONT_FACES)
    return f"""# GENERATED from app/frontend/design/tokens.py -- do not edit by hand.
# Regenerate: python -m app.frontend.design.streamlit_theme > .streamlit/config.toml
# (tests/frontend/test_streamlit_config.py fails if this file drifts.)

[browser]
gatherUsageStats = false

[client]
# "minimal" hides the Deploy button but keeps the menu (Settings > Theme).
toolbarMode = "minimal"

[server]
# Serves the bundled fonts (app/frontend/static/fonts) -- no third-party
# font request is ever made.
enableStaticServing = true

[theme]
font = "Inter"
headingFont = "Source Serif 4"
codeFont = "JetBrains Mono"
baseFontSize = 15
codeFontSize = "0.8125rem"
headingFontSizes = {_HEADING_SIZES}
headingFontWeights = {_HEADING_WEIGHTS}
metricValueFontSize = "1.75rem"
metricValueFontWeight = 600

{faces}
{_theme_block("light", LIGHT)}
{_theme_block("dark", DARK)}"""


if __name__ == "__main__":  # pragma: no cover - thin CLI
    print(render_config_toml(), end="")
