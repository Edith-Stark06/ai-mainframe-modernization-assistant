"""
UI primitives.

Purpose:
    The dashboard's visual vocabulary as pure functions: each returns a string
    of HTML styled by ``dashboard.css``. Nothing here fetches data or talks to
    Streamlit, so every primitive is unit-tested directly and every view shares
    one look.

Responsibilities:
    - Status: :func:`badge`, :func:`status_badge`, :func:`tone_for`.
    - Layout blocks: :func:`page_header`, :func:`kpi_grid`, :func:`stepper`,
      :func:`callout`, :func:`stage_grid`, :func:`empty_state`,
      :func:`key_values`, :func:`finding`, :func:`breadcrumbs`,
      :func:`brand`, :func:`workspace_card`, :func:`welcome_steps`.
    - Data: :func:`meter`, :func:`bar_chart` (with a table twin).
    - :func:`render` -- write HTML into the page.

Rules every primitive follows:
    * All caller text is HTML-escaped; only parameters named ``*_html`` are trusted.
    * Status is never color alone: a badge carries an icon *and* a word.
    * No blank lines or indentation in the output -- Markdown treats either as
      the end of an HTML block or the start of a code block.

Dependencies:
    - html (standard library); streamlit only inside :func:`render`.

Examples:
    >>> '<' in badge("a<b", "info").split(">", 1)[1].split("</span>")[0]
    False

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Sequence

from app.frontend.design import logo

__all__ = [
    "ICONS",
    "badge",
    "bar_chart",
    "brand_mark",
    "breadcrumbs",
    "brand",
    "callout",
    "empty_state",
    "finding",
    "icon",
    "key_values",
    "layer_diagram",
    "kpi_grid",
    "meter",
    "page_header",
    "render",
    "stage_grid",
    "status_badge",
    "stepper",
    "tone_for",
    "welcome_steps",
    "workspace_card",
]

# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------


def esc(value: object) -> str:
    """HTML-escape any value."""
    return html.escape(str(value), quote=True)


def compact(markup: str) -> str:
    """Remove the indentation and newlines Markdown would misread."""
    return re.sub(r"\s*\n\s*", "", markup.strip())


def render(markup: str) -> None:
    """Write already-built HTML into the Streamlit page."""
    import streamlit as st

    st.markdown(compact(markup), unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# icons (24px grid, stroke = currentColor)
# ----------------------------------------------------------------------------

ICONS: dict[str, str] = {
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
    "alert": '<path d="m21.7 18-8-14a2 2 0 0 0-3.5 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3"/><path d="M12 9v4M12 17h.01"/>',
    "minus": '<path d="M5 12h14"/>',
    "circle": '<circle cx="12" cy="12" r="8"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/>',
    "arrow": '<path d="M5 12h14M12 5l7 7-7 7"/>',
    "file": '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5z"/><path d="M14 2v6h6"/>',
    "upload": '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M5 20h14"/>',
    "folder": '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9l-.8-1.2A2 2 0 0 0 7.9 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z"/>',
    "spark": '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
}


def icon(name: str, *, size: int | None = None) -> str:
    """An inline SVG icon (decorative: ``aria-hidden``)."""
    inner = ICONS.get(name, ICONS["circle"])
    dim = f' width="{size}" height="{size}"' if size else ""
    return (
        f'<svg viewBox="0 0 24 24"{dim} fill="none" stroke="currentColor" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true" focusable="false">{inner}</svg>'
    )


# ----------------------------------------------------------------------------
# status
# ----------------------------------------------------------------------------

#: honest status word -> (tone, icon, display label)
_STATUS: dict[str, tuple[str, str, str]] = {
    "PASS": ("success", "check", "Pass"),
    "PASSED": ("success", "check", "Passed"),
    "SUCCESS": ("success", "check", "Success"),
    "VERIFIED": ("success", "check", "Verified"),
    "COMPLETE": ("success", "check", "Complete"),
    "DONE": ("success", "check", "Done"),
    "HEALTHY": ("success", "check", "Healthy"),
    "WARN": ("warning", "alert", "Warning"),
    "WARNING": ("warning", "alert", "Warning"),
    "PARTIAL": ("warning", "alert", "Partial"),
    "INCONCLUSIVE": ("warning", "alert", "Inconclusive"),
    "MEDIUM": ("warning", "alert", "Medium"),
    "FAIL": ("error", "x", "Fail"),
    "FAILED": ("error", "x", "Failed"),
    "FAILURE": ("error", "x", "Failure"),
    "ERROR": ("error", "x", "Error"),
    "HIGH": ("error", "x", "High"),
    "CRITICAL": ("error", "x", "Critical"),
    "LOW": ("neutral", "minus", "Low"),
    "IDLE": ("neutral", "minus", "Idle"),
    "NOT_RUN": ("neutral", "minus", "Not run"),
    "NOT RUN": ("neutral", "minus", "Not run"),
    "NOT_AVAILABLE": ("neutral", "minus", "Not available"),
    "NOT AVAILABLE": ("neutral", "minus", "Not available"),
    "UNAVAILABLE": ("neutral", "minus", "Unavailable"),
    "PENDING": ("neutral", "circle", "Pending"),
    "INFO": ("info", "info", "Info"),
}


def tone_for(status: str) -> str:
    """The tone (``success`` / ``warning`` / ``error`` / ``info`` / ``neutral``)
    for an honest backend status word; unknown words are neutral."""
    return _STATUS.get(status.strip().upper(), ("neutral", "minus", ""))[0]


def badge(label: str, tone: str = "neutral", glyph: str | None = None) -> str:
    """A pill: *glyph* icon (optional) and a *label*, in a tone's colors."""
    mark = icon(glyph) if glyph else ""
    return f'<span class="ds-badge ds-badge--{esc(tone)}">{mark}{esc(label)}</span>'


def status_badge(status: str, label: str | None = None) -> str:
    """A badge for a backend status word: icon + word, never color alone.

    Args:
        status: ``PASS`` / ``FAIL`` / ``INCONCLUSIVE`` / ``NOT_AVAILABLE`` / ...
        label: Text to show instead of the standard word for *status*.
    """
    tone, glyph, word = _STATUS.get(
        status.strip().upper(),
        ("neutral", "minus", status.replace("_", " ").strip().capitalize()),
    )
    return badge(label if label is not None else word, tone, glyph)


# ----------------------------------------------------------------------------
# page chrome
# ----------------------------------------------------------------------------


def page_header(
    title: str, subtitle: str | None = None, *, eyebrow: str | None = None
) -> str:
    """The page title block: optional eyebrow, serif title, one-line subtitle."""
    return compact(
        '<header class="ds-page-head">'
        + (f'<div class="ds-eyebrow">{esc(eyebrow)}</div>' if eyebrow else "")
        + f'<h1 class="ds-title">{esc(title)}</h1>'
        + (f'<p class="ds-subtitle">{esc(subtitle)}</p>' if subtitle else "")
        + "</header>"
    )


def brand_mark(size: int = 34) -> str:
    """The product logo on its dark tile (the same in light and dark themes)."""
    return logo.markup("tile", size=size, css_class="ds-brand-mark")


def brand(name: str = "Mainframe Modernization", tag: str = "COBOL to Java") -> str:
    """The sidebar brand block: mark + wordmark."""
    mark = brand_mark()
    return compact(
        f'<div class="ds-brand">{mark}<div class="ds-brand-name">{esc(name)}'
        f'<span class="ds-brand-tag">{esc(tag)}</span></div></div>'
    )


def workspace_card(workspace_id: str | None, detail: str | None = None) -> str:
    """The sidebar workspace summary: label, short id, one detail line."""
    if not workspace_id:
        body = '<div class="ds-ws-meta">No workspace open</div>'
    else:
        body = (
            f'<div class="ds-ws-id" title="{esc(workspace_id)}">{esc(workspace_id[:8])}</div>'
            + (f'<div class="ds-ws-meta">{esc(detail)}</div>' if detail else "")
        )
    return compact(
        f'<div class="ds-ws"><div class="ds-ws-label">Workspace</div>{body}</div>'
    )


def breadcrumbs(items: Sequence[str], *, file: str | None = None) -> str:
    """A breadcrumb trail; the last item is the current page. *file* is shown
    as a code chip before the page name."""
    parts: list[str] = []
    for i, item in enumerate(items):
        last = i == len(items) - 1
        parts.append(f'<span class="{"here" if last else ""}">{esc(item)}</span>')
        if not last:
            parts.append('<span class="sep" aria-hidden="true">/</span>')
    chip = f'<span class="file">{esc(file)}</span>' if file else ""
    return compact(
        f'<nav class="ds-crumbs" aria-label="Breadcrumb">{chip}'
        + ('<span class="sep" aria-hidden="true">/</span>' if file and items else "")
        + "".join(parts)
        + "</nav>"
    )


# ----------------------------------------------------------------------------
# blocks
# ----------------------------------------------------------------------------


def meter(
    name: str, ratio: float, detail: str | None = None, tone: str | None = None
) -> str:
    """A labelled meter for a 0..1 *ratio*. With no *tone* the fill follows the
    ratio (>= 0.9 success, >= 0.6 warning, else error)."""
    ratio = max(0.0, min(1.0, ratio))
    chosen = tone or (
        "success" if ratio >= 0.9 else "warning" if ratio >= 0.6 else "error"
    )
    pct = f"{ratio:.0%}"
    return compact(
        f'<div class="ds-meter"><div class="ds-meter-row"><span class="ds-meter-name">{esc(name)}</span>'
        f'<span class="ds-meter-value">{pct}</span></div>'
        f'<div class="ds-meter-track" role="progressbar" aria-label="{esc(name)}" '
        f'aria-valuemin="0" aria-valuemax="100" aria-valuenow="{round(ratio * 100)}">'
        f'<div class="ds-meter-fill ds-meter-fill--{chosen}" style="width:{ratio * 100:.1f}%"></div></div>'
        + (f'<div class="ds-meter-detail">{esc(detail)}</div>' if detail else "")
        + "</div>"
    )


def kpi_grid(items: Iterable[dict[str, object]]) -> str:
    """A responsive grid of stat tiles.

    Each item: ``label``, ``value`` (required); ``sub`` (one muted line);
    ``ratio`` (0..1, draws a meter under the value); ``ratio_tone``.
    """
    tiles: list[str] = []
    for item in items:
        ratio = item.get("ratio")
        bar = ""
        if isinstance(ratio, (int, float)):
            r = max(0.0, min(1.0, float(ratio)))
            tone = str(
                item.get("ratio_tone")
                or ("success" if r >= 0.9 else "warning" if r >= 0.6 else "error")
            )
            bar = (
                f'<div class="ds-meter-track" role="progressbar" aria-label="{esc(item["label"])}" '
                f'aria-valuemin="0" aria-valuemax="100" aria-valuenow="{round(r * 100)}">'
                f'<div class="ds-meter-fill ds-meter-fill--{esc(tone)}" style="width:{r * 100:.1f}%"></div></div>'
            )
        sub = (
            f'<div class="ds-kpi-sub">{esc(item["sub"])}</div>'
            if item.get("sub")
            else ""
        )
        tiles.append(
            f'<div class="ds-kpi"><div class="ds-kpi-label">{esc(item["label"])}</div>'
            f'<div class="ds-kpi-value">{esc(item["value"])}</div>{sub}{bar}</div>'
        )
    return compact(f'<div class="ds-kpis">{"".join(tiles)}</div>') if tiles else ""


_STEP_TONE = {
    "done": "success",
    "partial": "warning",
    "fail": "error",
    "pending": "neutral",
}
_STEP_ICON = {"done": "check", "partial": "alert", "fail": "x", "pending": "circle"}
_STEP_WORD = {
    "done": "Complete",
    "partial": "Needs review",
    "fail": "Failed",
    "pending": "Pending",
}


def stepper(steps: Sequence[dict[str, str]]) -> str:
    """The pipeline: connected steps, each with a state, a headline number and
    one detail line. Each step: ``name``, ``state`` (done / partial / fail /
    pending), ``metric``, ``detail``."""
    cells: list[str] = []
    for step in steps:
        state = step.get("state", "pending")
        if state not in _STEP_TONE:
            state = "pending"
        cells.append(
            f'<div class="ds-step ds-step--{state}" role="listitem"><div class="ds-step-top">'
            f'<span class="ds-step-name">{esc(step["name"])}</span>'
            f"{badge(_STEP_WORD[state], _STEP_TONE[state], _STEP_ICON[state])}</div>"
            f'<div class="ds-step-metric">{esc(step.get("metric", ""))}</div>'
            f'<div class="ds-step-detail">{esc(step.get("detail", ""))}</div></div>'
        )
    return (
        compact(f'<div class="ds-stepper" role="list">{"".join(cells)}</div>')
        if cells
        else ""
    )


def callout(
    tone: str,
    title: str,
    text: str | None = None,
    *,
    glyph: str | None = None,
    extra_html: str = "",
) -> str:
    """A banner with a status accent, a serif headline and one sentence."""
    chosen = glyph or {
        "success": "check",
        "warning": "alert",
        "error": "x",
        "info": "info",
    }.get(tone, "spark")
    return compact(
        f'<div class="ds-callout ds-callout--{esc(tone)}" role="status">'
        f'<div class="ds-callout-icon">{icon(chosen)}</div><div class="ds-callout-body">'
        f'<p class="ds-callout-title">{esc(title)}</p>'
        + (f'<div class="ds-callout-text">{esc(text)}</div>' if text else "")
        + f"{extra_html}</div></div>"
    )


def stage_grid(stages: Sequence[dict[str, str]]) -> str:
    """One chip per validation stage: name, status badge, one summary line."""
    chips = "".join(
        f'<div class="ds-stage"><div class="ds-stage-name">{esc(s["stage"])}</div>'
        f'{status_badge(s["status"])}'
        f'<div class="ds-stage-info">{esc(s.get("summary", ""))}</div></div>'
        for s in stages
    )
    return compact(f'<div class="ds-stages">{chips}</div>') if chips else ""


def empty_state(glyph: str, title: str, text: str) -> str:
    """An empty / not-yet state: what this is, why it is empty, how to start."""
    return compact(
        f'<div class="ds-empty"><div class="ds-empty-icon">{icon(glyph)}</div>'
        f'<div class="ds-empty-title">{esc(title)}</div><p class="ds-empty-text">{esc(text)}</p></div>'
    )


def welcome_steps(steps: Sequence[tuple[str, str]]) -> str:
    """Numbered onboarding steps: ``(title, text)`` pairs."""
    cells = "".join(
        f'<div class="ds-welcome-step"><div class="ds-welcome-num">{i}</div>'
        f'<div class="ds-welcome-title">{esc(t)}</div><div class="ds-welcome-text">{esc(x)}</div></div>'
        for i, (t, x) in enumerate(steps, 1)
    )
    return compact(f'<div class="ds-welcome">{cells}</div>')


def key_values(rows: Sequence[tuple[str, str]]) -> str:
    """A definition list of ``(label, value)`` pairs."""
    body = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in rows)
    return compact(f'<dl class="ds-kv">{body}</dl>')


def finding(
    title: str,
    text: str | None,
    status: str,
    label: str | None = None,
    *,
    full: bool = False,
) -> str:
    """One row of a findings list: severity badge, title, an explanatory line
    (clamped to two lines unless *full*)."""
    return compact(
        f'<div class="ds-finding{" ds-finding--full" if full else ""}"><div class="ds-finding-head">{status_badge(status, label)}'
        f'<span class="ds-finding-title">{esc(title)}</span></div>'
        + (f'<div class="ds-finding-text">{esc(text)}</div>' if text else "")
        + "</div>"
    )


def layer_diagram(layers: Sequence[tuple[str, Sequence[str], str]]) -> str:
    """Stacked layers joined by arrows: ``(label, chips, tone)`` per layer.

    The tone (``neutral`` / ``accent`` / ``success``) colors the chips of that
    layer. Layers are a *grouping*, not a claimed dataflow between the chips.
    """
    parts: list[str] = []
    for i, (label, chips, tone) in enumerate(layers):
        body = "".join(
            f'<span class="ds-chip ds-chip--{esc(tone)}">{esc(c)}</span>' for c in chips
        ) or ('<span class="ds-layer-empty">Nothing derived</span>')
        parts.append(
            f'<div class="ds-layer"><div class="ds-layer-label">{esc(label)}</div>'
            f'<div class="ds-chips">{body}</div></div>'
        )
        if i < len(layers) - 1:
            parts.append(
                f'<div class="ds-layer-arrow" aria-hidden="true">{icon("arrow")}</div>'
            )
    return compact(f'<div class="ds-layers">{"".join(parts)}</div>')


# ----------------------------------------------------------------------------
# charts
# ----------------------------------------------------------------------------


def bar_chart(
    rows: Sequence[tuple[str, int | float]],
    *,
    title: str,
    tone: str = "accent",
    tones: dict[str, str] | None = None,
    caption: str | None = None,
    max_rows: int = 8,
) -> str:
    """A horizontal bar chart for *nominal* categories.

    Follows the data-viz rules: one color for unordered categories (*tone*), or
    a fixed color per category in *tones* where the color is the category's
    meaning (severity); thin bars with a 4px data-end radius; the value at the
    bar tip; a ``title`` tooltip on every bar; and a visually-hidden table with
    the same numbers, so no value depends on seeing or hovering the bar.
    Rows beyond *max_rows* fold into one "Other" row.

    Args:
        rows: ``(category, value)`` pairs in display order.
        title: Accessible name of the chart (also the table caption).
        tone: Bar color for every row unless overridden in *tones*.
        tones: ``{category: tone}`` overrides.
        caption: One muted line under the chart.
        max_rows: Most rows to draw before folding the tail into "Other".
    """
    data = [(str(k), float(v)) for k, v in rows]
    if len(data) > max_rows:
        head, tail = data[: max_rows - 1], data[max_rows - 1 :]
        data = head + [("Other", sum(v for _, v in tail))]
    if not data:
        return ""
    top = max(v for _, v in data) or 1.0
    rendered: list[str] = []
    for name, value in data:
        width = max(value / top * 100.0, 1.5 if value else 0.0)
        bar_tone = (tones or {}).get(name, tone)
        cls = "" if bar_tone == "accent" else f" ds-bar-fill--{esc(bar_tone)}"
        shown = f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"
        rendered.append(
            f'<div class="ds-bar-name">{esc(name)}</div>'
            f'<div class="ds-bar-track"><div class="ds-bar-fill{cls}" style="width:{width:.1f}%" '
            f'title="{esc(name)}: {shown}"></div></div>'
            f'<div class="ds-bar-value">{shown}</div>'
        )
    twin = "".join(
        (
            f"<tr><td>{esc(n)}</td><td>{v:,.0f}</td></tr>"
            if float(v).is_integer()
            else f"<tr><td>{esc(n)}</td><td>{v:,.2f}</td></tr>"
        )
        for n, v in data
    )
    return compact(
        f'<figure class="ds-chart" style="margin:0" aria-label="{esc(title)}">'
        f'<div class="ds-bars" aria-hidden="true">{"".join(rendered)}</div>'
        f'<table class="ds-sr-only"><caption>{esc(title)}</caption>'
        f"<thead><tr><th>Category</th><th>Count</th></tr></thead><tbody>{twin}</tbody></table>"
        + (
            f'<figcaption class="ds-chart-caption">{esc(caption)}</figcaption>'
            if caption
            else ""
        )
        + "</figure>"
    )
