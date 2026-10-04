"""
The product logo.

Purpose:
    One definition of the mark -- three bars that loosen from a solid block
    (the legacy mainframe's data rows) toward a single cyan dot (the assistant
    and the modern output) -- from which every asset is generated: the in-app
    mark, the standalone SVGs and the browser-tab icon.

Responsibilities:
    - :func:`markup` -- the SVG for a variant, sized for inline or file use.
    - :func:`write_assets` -- regenerate ``app/frontend/static/logo``.
    - ``python -m app.frontend.design.logo`` -- regenerate the assets.

Non-responsibilities:
    - The wordmark; it is live text beside the mark (see
      :func:`app.frontend.design.ui.brand`) so it stays crisp and translatable.

Dependencies:
    - pillow (favicon rendering only, imported lazily)

Examples:
    >>> markup("tile", size=34).startswith("<svg")
    True

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal, get_args

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

__all__ = ["ASSET_DIR", "Variant", "markup", "write_assets"]

Variant = Literal["tile", "on-dark", "on-light"]

ASSET_DIR = Path(__file__).resolve().parent.parent / "static" / "logo"

# Fixed brand colors: the logo looks the same in both themes.
_TILE = "#0D1117"
_BAR_ON_DARK = "#E6EDF3"
_DOT_ON_DARK = "#2DD4E8"
_BAR_ON_LIGHT = "#0B1620"
_DOT_ON_LIGHT = "#0A6C86"

# Geometry on a 64-unit grid: ``(x, y, width)`` per bar, shared height and
# radius, the dot, and the tile. The content is centered horizontally.
_VIEWBOX = 64
_TILE_RADIUS = 14
_BARS = ((11.5, 18, 22), (11.5, 29, 30), (11.5, 40, 26))
_BAR_HEIGHT = 6
_BAR_RADIUS = 2
_DOT = (48.5, 32, 4.5)  # cx, cy, r

_PALETTE: dict[str, tuple[str, str]] = {
    "tile": (_BAR_ON_DARK, _DOT_ON_DARK),
    "on-dark": (_BAR_ON_DARK, _DOT_ON_DARK),
    "on-light": (_BAR_ON_LIGHT, _DOT_ON_LIGHT),
}


def markup(
    variant: Variant = "tile",
    *,
    size: int | None = None,
    css_class: str | None = None,
    title: str | None = None,
) -> str:
    """The logo as a single-line ``<svg>``.

    Args:
        variant: ``"tile"`` (on a dark rounded square), ``"on-dark"`` (symbol
            only, for dark backgrounds) or ``"on-light"`` (for light ones).
        size: Rendered width and height in pixels; omit to let CSS size it.
        css_class: Optional class for the root element.
        title: Accessible name. Without one the mark is decorative
            (``aria-hidden``), which is right beside a visible wordmark.
    """
    bar, dot = _PALETTE[variant]
    attrs = f'viewBox="0 0 {_VIEWBOX} {_VIEWBOX}" xmlns="http://www.w3.org/2000/svg"'
    if size:
        attrs += f' width="{size}" height="{size}"'
    if css_class:
        attrs += f' class="{css_class}"'
    attrs += f' role="img" aria-label="{title}"' if title else ' aria-hidden="true"'
    parts = [f"<svg {attrs}>"]
    if title:
        parts.append(f"<title>{title}</title>")
    if variant == "tile":
        parts.append(
            f'<rect width="{_VIEWBOX}" height="{_VIEWBOX}" rx="{_TILE_RADIUS}" fill="{_TILE}"/>'
        )
    for x, y, width in _BARS:
        parts.append(
            f'<rect x="{x}" y="{y}" width="{width}" height="{_BAR_HEIGHT}" '
            f'rx="{_BAR_RADIUS}" fill="{bar}"/>'
        )
    cx, cy, r = _DOT
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{dot}"/>')
    parts.append("</svg>")
    return "".join(parts)


def _favicon(pixels: int = 256) -> PILImage:
    """The tile variant rasterised with 4x supersampling (a Pillow image)."""
    from PIL import Image, ImageDraw

    scale = pixels * 4 / _VIEWBOX
    canvas = Image.new("RGBA", (pixels * 4, pixels * 4), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (0, 0, pixels * 4 - 1, pixels * 4 - 1), _TILE_RADIUS * scale, fill=_TILE
    )
    for x, y, width in _BARS:
        draw.rounded_rectangle(
            (x * scale, y * scale, (x + width) * scale, (y + _BAR_HEIGHT) * scale),
            _BAR_RADIUS * scale,
            fill=_BAR_ON_DARK,
        )
    cx, cy, r = _DOT
    draw.ellipse(
        ((cx - r) * scale, (cy - r) * scale, (cx + r) * scale, (cy + r) * scale),
        fill=_DOT_ON_DARK,
    )
    return canvas.resize((pixels, pixels), Image.Resampling.LANCZOS)


def write_assets(directory: Path = ASSET_DIR) -> list[Path]:
    """Write the SVG variants and ``favicon.png``; returns the paths written."""
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    names = {
        "tile": "logo-mark.svg",
        "on-dark": "logo-symbol-on-dark.svg",
        "on-light": "logo-symbol-on-light.svg",
    }
    for variant in get_args(Variant):
        path = directory / names[variant]
        path.write_text(
            markup(variant, title="Mainframe Modernization") + "\n", encoding="utf-8"
        )
        written.append(path)
    icon = directory / "favicon.png"
    _favicon().save(icon, optimize=True)
    written.append(icon)
    return written


if __name__ == "__main__":  # pragma: no cover - thin CLI
    for written_path in write_assets():
        print(written_path)
