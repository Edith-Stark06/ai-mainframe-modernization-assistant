"""
Tests for the design system's rendering layer.

Covers the HTML primitives (:mod:`app.frontend.design.ui`), the stylesheet
(:mod:`app.frontend.design.styles` and the ``*.css`` files) and the generated
Streamlit theme config. The colour values themselves are covered in
``test_design_tokens.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.frontend.design import styles, ui
from app.frontend.design.streamlit_theme import render_config_toml
from app.frontend.design.tokens import DARK, LIGHT

DESIGN_DIR = Path(__file__).resolve().parents[2] / "app" / "frontend" / "design"
CONFIG = Path(__file__).resolve().parents[2] / ".streamlit" / "config.toml"
STYLESHEETS = sorted(DESIGN_DIR.glob("*.css"))


# --------------------------------------------------------------- escaping


def test_user_text_is_escaped_in_every_primitive() -> None:
    evil = '<img src=x onerror="alert(1)">'
    outputs = [
        ui.badge(evil),
        ui.status_badge("PASS", evil),
        ui.page_header(evil, evil, eyebrow=evil),
        ui.callout("info", evil, evil),
        ui.empty_state("file", evil, evil),
        ui.finding(evil, evil, "HIGH"),
        ui.key_values([(evil, evil)]),
        ui.kpi_grid([{"label": evil, "value": evil, "sub": evil}]),
        ui.stepper([{"name": evil, "state": "done", "metric": evil, "detail": evil}]),
        ui.stage_grid([{"stage": evil, "status": "PASS", "summary": evil}]),
        ui.breadcrumbs([evil], file=evil),
        ui.workspace_card(evil, evil),
        ui.bar_chart([(evil, 3)], title=evil, caption=evil),
        ui.layer_diagram([(evil, [evil], "neutral")]),
    ]
    for html in outputs:
        assert "<img" not in html
        assert "&lt;img" in html


def test_compact_markup_has_no_blank_lines_or_indentation() -> None:
    """Markdown turns a blank line or 4-space indent into a code block."""
    for html in (ui.page_header("T", "S"), ui.callout("info", "T", "S"), ui.brand()):
        assert "\n" not in html


# ----------------------------------------------------------------- status


@pytest.mark.parametrize(
    ("status", "tone"),
    [
        ("PASS", "success"),
        ("pass", "success"),
        ("INCONCLUSIVE", "warning"),
        ("FAIL", "error"),
        ("HIGH", "error"),
        ("NOT_AVAILABLE", "neutral"),
        ("something-new", "neutral"),
    ],
)
def test_tone_for_maps_honest_words(status: str, tone: str) -> None:
    assert ui.tone_for(status) == tone


def test_status_is_never_color_alone() -> None:
    """Every status badge carries an icon and a word, not only a colour."""
    for word in ("PASS", "FAIL", "INCONCLUSIVE", "NOT_AVAILABLE", "PENDING"):
        html = ui.status_badge(word)
        assert "<svg" in html
        assert re.search(r">[A-Za-z ]+</span>$", html)


def test_an_unknown_status_is_shown_neutral_not_green() -> None:
    assert "ds-badge--neutral" in ui.status_badge("brand-new-state")


def test_stepper_is_a_list_of_list_items() -> None:
    """A role=list needs listitem children (axe: aria-required-children)."""
    html = ui.stepper([{"name": "A", "state": "done"}, {"name": "B", "state": "fail"}])
    assert 'role="list"' in html
    assert html.count('role="listitem"') == 2


def test_stepper_unknown_state_falls_back_to_pending() -> None:
    html = ui.stepper([{"name": "A", "state": "bogus"}])
    assert "ds-step--pending" in html


# ----------------------------------------------------------------- blocks


def test_meter_clamps_and_exposes_progressbar_semantics() -> None:
    html = ui.meter("Coverage", 1.7)
    assert 'role="progressbar"' in html
    assert 'aria-valuenow="100"' in html
    assert "ds-meter-fill--success" in html


def test_kpi_ratio_tone_follows_the_value() -> None:
    assert "ds-meter-fill--error" in ui.kpi_grid(
        [{"label": "x", "value": "10%", "ratio": 0.1}]
    )
    assert "ds-meter-fill--warning" in ui.kpi_grid(
        [{"label": "x", "value": "70%", "ratio": 0.7}]
    )


def test_kpi_grid_with_no_items_renders_nothing() -> None:
    assert ui.kpi_grid([]) == ""


def test_bar_chart_has_a_table_twin_and_folds_the_tail() -> None:
    rows = [(f"c{i}", i + 1) for i in range(12)]
    html = ui.bar_chart(rows, title="T", max_rows=5)
    assert "<table" in html
    assert html.count('class="ds-bar-name"') == 5
    assert ">Other<" in html
    # the folded row is the sum of the tail: c4..c11 -> 5+6+...+12 = 68
    assert "68" in html


def test_bar_chart_with_no_rows_renders_nothing() -> None:
    assert ui.bar_chart([], title="T") == ""


def test_bar_widths_are_proportional_with_a_visible_minimum() -> None:
    html = ui.bar_chart([("big", 100), ("tiny", 1)], title="T")
    assert "width:100.0%" in html
    assert "width:1.5%" in html


def test_layer_diagram_marks_an_empty_layer() -> None:
    html = ui.layer_diagram([("Target", [], "accent")])
    assert "Nothing derived" in html


def test_breadcrumbs_mark_the_current_page() -> None:
    html = ui.breadcrumbs(["Workspace", "Overview"], file="A.cbl")
    assert 'class="here">Overview' in html
    assert 'aria-label="Breadcrumb"' in html


# ------------------------------------------------------------ stylesheets


@pytest.mark.parametrize("sheet", STYLESHEETS, ids=lambda p: p.name)
def test_stylesheets_use_tokens_not_literal_colours(sheet: Path) -> None:
    """Colour lives in tokens.py only, so light and dark can never drift."""
    text = re.sub(r"/\*.*?\*/", "", sheet.read_text(encoding="utf-8"), flags=re.S)
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", text), "hex colour literal"
    assert not re.search(r"\brgba?\(", text), "rgb()/rgba() colour literal"


@pytest.mark.parametrize("sheet", STYLESHEETS, ids=lambda p: p.name)
def test_stylesheets_only_use_defined_tokens(sheet: Path) -> None:
    defined = set(re.findall(r"--[a-z0-9-]+(?=:)", styles.root_block(LIGHT)))
    text = re.sub(r"/\*.*?\*/", "", sheet.read_text(encoding="utf-8"), flags=re.S)
    used = set(re.findall(r"var\((--[a-z0-9-]+)", text))
    assert used <= defined | {"--st-font"}, sorted(used - defined)


def test_light_and_dark_define_identical_token_names() -> None:
    names = lambda block: re.findall(r"--[a-z0-9-]+(?=:)", block)  # noqa: E731
    assert names(styles.root_block(LIGHT)) == names(styles.root_block(DARK))


def test_build_css_includes_fonts_tokens_and_extras() -> None:
    css = styles.build_css("dark", extra=("chat.css",))
    assert "@font-face" in css
    assert "color-scheme: dark" in css
    assert ".st-key-chat_thread" in css


def test_unknown_theme_falls_back_to_light() -> None:
    assert "color-scheme: light" in styles.build_css("sepia")
    assert "color-scheme: light" in styles.build_css(None)


def test_active_theme_defaults_to_light_outside_a_browser() -> None:
    assert styles.active_theme() == "light"


def test_bundled_fonts_exist() -> None:
    static = DESIGN_DIR.parent / "static" / "fonts"
    for name in ("Inter-Variable", "SourceSerif4-Variable", "JetBrainsMono-Variable"):
        assert (static / f"{name}.woff2").stat().st_size > 10_000


# ----------------------------------------------------- generated config


def test_streamlit_config_is_in_sync_with_the_tokens() -> None:
    assert (
        CONFIG.read_text(encoding="utf-8").replace("\r\n", "\n") == render_config_toml()
    )
