"""
The product logo: one geometry, every asset generated from it.

Covers the SVG variants, the committed assets staying in sync with the
generator (so nobody edits an SVG by hand and drifts from the in-app mark),
the favicon, and the logo's use in the app and the landing page.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from PIL import Image

from app.frontend.design import logo, ui

NAMES = {
    "tile": "logo-mark.svg",
    "on-dark": "logo-symbol-on-dark.svg",
    "on-light": "logo-symbol-on-light.svg",
}


@pytest.mark.parametrize("variant", ["tile", "on-dark", "on-light"])
def test_every_variant_is_three_bars_and_a_dot(variant: str) -> None:
    svg = logo.markup(variant)  # type: ignore[arg-type]
    bars = svg.count('rx="2"')
    assert bars == 3
    assert svg.count("<circle") == 1
    assert svg.startswith("<svg") and svg.endswith("</svg>")


def test_only_the_tile_variant_has_a_background() -> None:
    assert 'rx="14"' in logo.markup("tile")
    assert 'rx="14"' not in logo.markup("on-dark")
    assert 'rx="14"' not in logo.markup("on-light")


def test_the_mark_is_decorative_unless_it_has_a_title() -> None:
    assert 'aria-hidden="true"' in logo.markup("tile")
    named = logo.markup("tile", title="Mainframe Modernization")
    assert 'role="img"' in named and "<title>Mainframe Modernization</title>" in named
    assert "aria-hidden" not in named


def test_the_light_variant_keeps_the_dot_readable_on_white() -> None:
    """The dark-theme cyan is too pale on white, so the light variant is deeper."""
    from app.frontend.design.tokens import contrast_ratio

    assert contrast_ratio("#0A6C86", "#FFFFFF") >= 3.0
    assert contrast_ratio("#2DD4E8", "#0D1117") >= 3.0
    assert "#0A6C86" in logo.markup("on-light")
    assert "#2DD4E8" in logo.markup("on-dark")


def test_content_is_horizontally_centered_on_the_tile() -> None:
    """Left margin and right margin differ by less than a bar's corner radius."""
    xs = [x for x, _, _ in logo._BARS]
    right = max(x + w for x, _, w in logo._BARS)
    cx, _, r = logo._DOT
    right = max(right, cx + r)
    left_margin = min(xs)
    right_margin = logo._VIEWBOX - right
    assert abs(left_margin - right_margin) < 1.0


@pytest.mark.parametrize("variant", ["tile", "on-dark", "on-light"])
def test_committed_svgs_match_the_generator(variant: str) -> None:
    committed = (logo.ASSET_DIR / NAMES[variant]).read_text(encoding="utf-8")
    expected = logo.markup(variant, title="Mainframe Modernization") + "\n"  # type: ignore[arg-type]
    assert committed.replace("\r\n", "\n") == expected


def test_the_favicon_is_a_256px_png_with_the_cyan_dot() -> None:
    icon = Image.open(logo.ASSET_DIR / "favicon.png").convert("RGBA")
    assert icon.size == (256, 256)
    assert icon.getpixel((0, 0))[3] == 0  # transparent corner of the tile
    r, g, b, a = icon.getpixel((int(48.5 / 64 * 256), 128))
    assert (r, g, b) == pytest.approx((0x2D, 0xD4, 0xE8), abs=6) and a == 255


def test_write_assets_regenerates_into_any_directory(tmp_path: Path) -> None:
    written = logo.write_assets(tmp_path)
    assert {p.name for p in written} == set(NAMES.values()) | {"favicon.png"}
    assert all(p.stat().st_size > 0 for p in written)


def test_the_in_app_mark_is_the_logo() -> None:
    html = ui.brand_mark(40)
    assert 'class="ds-brand-mark"' in html
    assert 'width="40"' in html and html.count("<circle") == 1
    assert "\n" not in html


def test_the_sidebar_brand_uses_the_logo_and_the_product_name() -> None:
    html = ui.brand()
    assert "ds-brand-mark" in html and "Mainframe Modernization" in html


def test_the_landing_page_uses_the_logo_not_the_old_icon() -> None:
    from app.frontend.landing_template import LANDING_HTML

    assert "{LOGO}" in LANDING_HTML
    assert "brand-icon" not in LANDING_HTML


def test_app_uses_the_favicon_file() -> None:
    source = (
        Path(__file__).resolve().parents[2] / "app" / "frontend" / "app.py"
    ).read_text(encoding="utf-8")
    assert re.search(r"page_icon=str\(FAVICON\)", source)
    assert (logo.ASSET_DIR / "favicon.png").exists()
