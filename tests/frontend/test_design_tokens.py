"""
The design tokens meet WCAG 2.1 AA, in both palettes.

Purpose:
    ``DESIGN.md``'s own values fail AA in several places (white on its coral
    button is 3.28:1, its coral link 3.11:1, its success/warning text about
    2.3:1). The dashboard therefore uses adjusted tokens; this test is what
    keeps them honest -- a color change that drops a pair below its threshold
    fails here, not in a user's eyes.
"""

from __future__ import annotations

import pytest

from app.frontend.design.tokens import (
    DARK,
    LIGHT,
    MARK_PAIRS,
    TEXT_PAIRS,
    Palette,
    contrast_ratio,
    palette_for,
)

PALETTES = [LIGHT, DARK]


@pytest.mark.parametrize("palette", PALETTES, ids=lambda p: p.name)
@pytest.mark.parametrize(("fg", "bg"), TEXT_PAIRS, ids=lambda v: str(v))
def test_text_pairs_reach_4_5_to_1(palette: Palette, fg: str, bg: str) -> None:
    ratio = contrast_ratio(getattr(palette, fg), getattr(palette, bg))
    assert ratio >= 4.5, f"{palette.name}: {fg} on {bg} is {ratio:.2f}:1 (needs 4.5:1)"


@pytest.mark.parametrize("palette", PALETTES, ids=lambda p: p.name)
@pytest.mark.parametrize(("fg", "bg"), MARK_PAIRS, ids=lambda v: str(v))
def test_marks_reach_3_to_1(palette: Palette, fg: str, bg: str) -> None:
    ratio = contrast_ratio(getattr(palette, fg), getattr(palette, bg))
    assert ratio >= 3.0, f"{palette.name}: {fg} on {bg} is {ratio:.2f}:1 (needs 3:1)"


def test_contrast_ratio_matches_known_values() -> None:
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast_ratio("#ffffff", "#ffffff") == pytest.approx(1.0)
    assert contrast_ratio("#141413", "#faf9f5") == pytest.approx(17.5, abs=0.1)
    # symmetric
    assert contrast_ratio("#a9583e", "#ffffff") == contrast_ratio("#ffffff", "#a9583e")


def test_the_design_md_values_this_replaces_really_do_fail() -> None:
    """If these ever pass, the adjustments above are no longer needed."""
    assert contrast_ratio("#ffffff", "#cc785c") < 4.5  # its button
    assert contrast_ratio("#cc785c", "#faf9f5") < 4.5  # its coral link
    assert contrast_ratio("#5db872", "#faf9f5") < 4.5  # its success text
    assert contrast_ratio("#d4a017", "#faf9f5") < 4.5  # its warning text


def test_every_palette_field_is_a_hex_color() -> None:
    for palette in PALETTES:
        for field, value in vars(palette).items():
            if field == "name":
                continue
            assert isinstance(value, str) and len(value) == 7 and value[0] == "#", (
                palette.name,
                field,
                value,
            )
            int(value[1:], 16)  # parses


def test_the_two_palettes_define_the_same_fields() -> None:
    assert vars(LIGHT).keys() == vars(DARK).keys()


@pytest.mark.parametrize(
    ("theme", "expected"),
    [
        ("dark", DARK),
        ("DARK", DARK),
        ("light", LIGHT),
        (None, LIGHT),
        ("", LIGHT),
        ("x", LIGHT),
    ],
)
def test_palette_for(theme: str | None, expected: Palette) -> None:
    assert palette_for(theme) is expected
