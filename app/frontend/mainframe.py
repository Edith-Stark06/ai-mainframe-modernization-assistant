"""
Phase 12 — the virtual mainframe / AI Core diagram.

This is the product's persistent visual identity: a schematic SVG of
the legacy mainframe, its subsystems, the AI Core, and (once real
architecture exists) the modern components it produced.

Design constraints this module honors:

* No custom Streamlit component build (no React/JS toolchain) -- pure
  SVG + CSS keyframe animation, per the Phase 12 technology constraint.
* Streamlit cannot route an arbitrary in-page SVG click back into
  Python without a custom bidirectional component. Rather than fake
  interactivity, each subsystem is rendered TWICE: once inside the
  animated SVG (decorative, CSS ``:hover`` only) and once as a real
  ``st.button`` directly beneath it, sharing the same label/icon so the
  two read as one connected control. Clicking the button is the actual
  navigation; the SVG node is the visual anchor for it.
* Every illuminated/colored state is driven by :class:`ChipState`,
  which is computed from real backend data by ``compute_chip_state``.
  The "modern architecture" side of the diagram only ever names real
  generated components when ``architecture_components`` is given; the
  in-diagram label reads ``ARCHITECTURE AWAITING ANALYSIS`` otherwise.
  ``mode="concept"`` is the one deliberate exception, used only on the
  logged-out landing page to illustrate the product idea in the
  abstract -- never inside a workspace bound to a real program.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Sequence

import streamlit as st

__all__ = [
    "ChipState",
    "Subsystem",
    "SUBSYSTEMS",
    "compute_chip_state",
    "render_ai_core_status",
    "render_mainframe_diagram",
    "render_subsystem_nav",
]


class ChipState(str, Enum):
    """The AI Core's state. Every value must be a direct rendering of a
    real backend fact -- see ``compute_chip_state``.

    JAVA_GENERATED / COMPILED / BEHAVIOR_INCONCLUSIVE / BEHAVIOR_FAIL /
    VERIFIED are defined here for forward-compatibility with the design
    brief (docs/PHASE12_DESIGN.md) but are currently UNREACHABLE: no API
    route exists yet for Java generation, compilation, behavioral
    validation, or the Phase 11 quality loop (see the PR description's
    documented scope decision). They must not be produced until that
    backend surface exists.
    """

    IDLE = "IDLE"
    ANALYZING = "ANALYZING"
    ANALYSIS_COMPLETE = "ANALYSIS_COMPLETE"
    WARNING = "WARNING"
    JAVA_GENERATED = "JAVA_GENERATED"
    COMPILED = "COMPILED"
    BEHAVIOR_INCONCLUSIVE = "BEHAVIOR_INCONCLUSIVE"
    BEHAVIOR_FAIL = "BEHAVIOR_FAIL"
    VERIFIED = "VERIFIED"


_CHIP_LABEL = {
    ChipState.IDLE: "AWAITING ANALYSIS",
    ChipState.ANALYZING: "ANALYZING",
    ChipState.ANALYSIS_COMPLETE: "ANALYSIS COMPLETE",
    ChipState.WARNING: "RISKS DETECTED",
    ChipState.JAVA_GENERATED: "JAVA GENERATED",
    ChipState.COMPILED: "COMPILED",
    ChipState.BEHAVIOR_INCONCLUSIVE: "BEHAVIOR INCONCLUSIVE",
    ChipState.BEHAVIOR_FAIL: "BEHAVIOR FAIL",
    ChipState.VERIFIED: "VERIFIED",
}
_CHIP_STATUS_WORD = {
    ChipState.IDLE: "IDLE",
    ChipState.ANALYZING: "IDLE",
    ChipState.ANALYSIS_COMPLETE: "PASS",
    ChipState.WARNING: "WARNING",
    ChipState.JAVA_GENERATED: "PASS",
    ChipState.COMPILED: "PASS",
    ChipState.BEHAVIOR_INCONCLUSIVE: "INCONCLUSIVE",
    ChipState.BEHAVIOR_FAIL: "FAIL",
    ChipState.VERIFIED: "PASS",
}


def compute_chip_state(
    *,
    has_analysis_result: bool,
    is_loading: bool,
    insufficient_data: bool,
    risk_count: int,
) -> ChipState:
    """Derive the AI Core's state purely from real, already-fetched
    backend facts. No timers, no guesses."""
    if is_loading:
        return ChipState.ANALYZING
    if not has_analysis_result:
        return ChipState.IDLE
    if insufficient_data or risk_count > 0:
        return ChipState.WARNING
    return ChipState.ANALYSIS_COMPLETE


@dataclass(frozen=True)
class Subsystem:
    key: str
    label: str
    description: str
    #: which workspace tab clicking this subsystem should open
    target_tab: str


SUBSYSTEMS: Sequence[Subsystem] = (
    Subsystem(
        "identification",
        "IDENTIFICATION",
        "Program identity, source metadata, and analysis coverage.",
        "Overview",
    ),
    Subsystem(
        "data",
        "DATA",
        "Working-storage fields and variable-level references.",
        "Dependencies",
    ),
    Subsystem(
        "procedure",
        "PROCEDURE",
        "Control flow, paragraphs, and business logic (Flow tab, in Overview).",
        "Overview",
    ),
    Subsystem(
        "files",
        "FILES",
        "Source inventory for the active workspace.",
        "Overview",
    ),
    Subsystem(
        "dependencies",
        "DEPENDENCIES",
        "Cross-program CALL / PERFORM / COPY graph.",
        "Dependencies",
    ),
)


def render_ai_core_status(state: ChipState) -> None:
    """A compact, honest status line -- used wherever the diagram itself
    is not shown but the current AI Core state still needs to be legible
    (e.g. the sidebar)."""
    from app.frontend.theme import status_pill

    st.markdown(
        f'<div class="mf-panel" style="text-align:center;">'
        f'<div class="mf-muted" style="font-size:0.72rem;letter-spacing:0.08em;">AI CORE</div>'
        f"{status_pill(_CHIP_LABEL[state], _CHIP_STATUS_WORD[state])}"
        f"</div>",
        unsafe_allow_html=True,
    )


def _subsystem_illumination(state: ChipState) -> str:
    """CSS class applied to every subsystem node once analysis exists."""
    if state in (ChipState.IDLE, ChipState.ANALYZING):
        return "mf-node-dim"
    if state is ChipState.WARNING or state is ChipState.BEHAVIOR_FAIL:
        return "mf-node-warn"
    return "mf-node-lit"


def _core_illumination_class(state: ChipState) -> str:
    return {
        ChipState.IDLE: "mf-core-idle",
        ChipState.ANALYZING: "mf-core-analyzing",
        ChipState.ANALYSIS_COMPLETE: "mf-core-lit",
        ChipState.WARNING: "mf-core-warn",
        ChipState.JAVA_GENERATED: "mf-core-lit",
        ChipState.COMPILED: "mf-core-lit",
        ChipState.BEHAVIOR_INCONCLUSIVE: "mf-core-warn",
        ChipState.BEHAVIOR_FAIL: "mf-core-fail",
        ChipState.VERIFIED: "mf-core-verified",
    }[state]


_DIAGRAM_CSS = """
<style>
  .mf-diagram-wrap { position: relative; }
  .mf-diagram svg { width: 100%; height: auto; display: block; }

  .mf-node rect {
    fill: #0d1117;
    stroke: #1c2733;
    stroke-width: 1.2;
    transition: stroke 0.25s ease, filter 0.25s ease;
  }
  .mf-node text { fill: #8b98a5; font-size: 11px; letter-spacing: 0.04em; }
  .mf-node:hover rect { stroke: #2dd4e8; filter: drop-shadow(0 0 6px rgba(45,212,232,0.5)); }
  .mf-node:hover text { fill: #2dd4e8; }

  .mf-node-dim rect { stroke: #1c2733; }
  .mf-node-lit rect { stroke: #3ddc97; filter: drop-shadow(0 0 4px rgba(61,220,151,0.35)); }
  .mf-node-lit text { fill: #3ddc97; }
  .mf-node-warn rect { stroke: #e8a92d; filter: drop-shadow(0 0 4px rgba(232,169,45,0.35)); }
  .mf-node-warn text { fill: #e8a92d; }

  .mf-core-shell {
    fill: none; stroke-width: 1.4;
    transform-origin: center;
  }
  .mf-core-idle { color: #1c2733; }
  .mf-core-analyzing { color: #2dd4e8; }
  .mf-core-lit { color: #2dd4e8; }
  .mf-core-warn { color: #e8a92d; }
  .mf-core-fail { color: #e84d4d; }
  .mf-core-verified { color: #3ddc97; }

  .mf-core-idle .mf-core-shell { stroke: #1c2733; }
  .mf-core-analyzing .mf-core-shell { stroke: #2dd4e8; animation: mf-spin 3.5s linear infinite; }
  .mf-core-lit .mf-core-shell { stroke: #2dd4e8; filter: drop-shadow(0 0 10px rgba(45,212,232,0.55)); }
  .mf-core-warn .mf-core-shell { stroke: #e8a92d; filter: drop-shadow(0 0 10px rgba(232,169,45,0.55)); }
  .mf-core-fail .mf-core-shell { stroke: #e84d4d; filter: drop-shadow(0 0 10px rgba(232,77,77,0.55)); }
  .mf-core-verified .mf-core-shell { stroke: #3ddc97; filter: drop-shadow(0 0 12px rgba(61,220,151,0.65)); }

  .mf-core-label { fill: #e6edf3; font-size: 12px; font-weight: 700; letter-spacing: 0.06em; }

  .mf-core-idle .mf-core-pulse, .mf-core-analyzing .mf-core-pulse { opacity: 0; }
  .mf-core-lit .mf-core-pulse, .mf-core-warn .mf-core-pulse,
  .mf-core-fail .mf-core-pulse, .mf-core-verified .mf-core-pulse {
    animation: mf-breathe 2.6s ease-in-out infinite;
  }

  .mf-flow-line {
    stroke: #1c2733;
    stroke-width: 1.4;
    fill: none;
  }
  .mf-flow-line.mf-flow-active {
    stroke: #2dd4e8;
    stroke-dasharray: 6 6;
    animation: mf-flow 1.6s linear infinite;
  }

  .mf-arch-pill rect { fill: #0d1117; stroke: #1c2733; }
  .mf-arch-pill text { fill: #8b98a5; font-size: 10px; }
  .mf-arch-pill.mf-arch-real rect { stroke: #3ddc97; }
  .mf-arch-pill.mf-arch-real text { fill: #3ddc97; }

  @keyframes mf-flow { to { stroke-dashoffset: -24; } }
  @keyframes mf-breathe {
    0%, 100% { opacity: 0.55; r: 46; }
    50% { opacity: 0.95; r: 50; }
  }
  @keyframes mf-spin { to { transform: rotate(360deg); } }
  @keyframes mf-node-in {
    from { opacity: 0; transform: translateX(-6px); }
    to { opacity: 1; transform: translateX(0); }
  }
  @keyframes mf-core-in {
    from { opacity: 0; transform: scale(0.85); }
    to { opacity: 1; transform: scale(1); }
  }

  /* boot-in sequence: played once on first landing render; every later
     render (booted=False) shows the settled end-state with no animation */
  .mf-boot .mf-node { animation: mf-node-in 0.5s ease both; }
  .mf-boot .mf-core-shell, .mf-boot .mf-core-label {
    animation: mf-core-in 0.6s ease 0.5s both;
  }

  @media (prefers-reduced-motion: reduce) {
    .mf-core-analyzing .mf-core-shell { animation: none; }
    .mf-flow-line.mf-flow-active { animation: none; }
    .mf-core-lit .mf-core-pulse, .mf-core-warn .mf-core-pulse,
    .mf-core-fail .mf-core-pulse, .mf-core-verified .mf-core-pulse { animation: none; }
    .mf-boot .mf-node, .mf-boot .mf-core-shell, .mf-boot .mf-core-label { animation: none; }
  }
</style>
"""


def _node_svg(
    x: int, y: int, w: int, h: int, label: str, css_class: str, delay: float
) -> str:
    return (
        f'<g class="mf-node {css_class}" style="animation-delay:{delay}s">'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6"/>'
        f'<text x="{x + w / 2}" y="{y + h / 2 + 4}" text-anchor="middle">{label}</text>'
        f"</g>"
    )


def render_mainframe_diagram(
    state: ChipState,
    *,
    mode: str = "live",
    architecture_components: Sequence[str] | None = None,
    play_boot: bool = False,
) -> None:
    """Render the mainframe -> AI Core -> modern-architecture SVG.

    ``mode="concept"`` is only for the logged-out landing page: the
    architecture side shows illustrative component names to explain the
    product idea. ``mode="live"`` is for the workspace: it shows real
    ``architecture_components`` when given, else the honest
    ``ARCHITECTURE AWAITING ANALYSIS`` placeholder -- never fabricated.

    ``play_boot=True`` plays the one-time staggered power-on animation
    (used the first time the landing page is shown in a session);
    every subsequent render uses ``play_boot=False`` and shows the
    settled end-state immediately, per the "do not force a replay"
    requirement.
    """
    st.markdown(_DIAGRAM_CSS, unsafe_allow_html=True)

    core_cls = _core_illumination_class(state)
    node_cls = _subsystem_illumination(state)
    flow_active = "mf-flow-active" if state is not ChipState.IDLE else ""
    boot_cls = "mf-boot" if play_boot else ""

    subsystem_nodes = "".join(
        _node_svg(
            20, 20 + i * 44, 150, 34, s.label, node_cls, i * 0.12 if play_boot else 0
        )
        for i, s in enumerate(SUBSYSTEMS)
    )
    connectors = "".join(
        f'<path class="mf-flow-line {flow_active}" '
        f'd="M170,{37 + i * 44} C 260,{37 + i * 44} 260,150 330,150"/>'
        for i in range(len(SUBSYSTEMS))
    )

    if mode == "concept":
        arch_items = architecture_components or [
            "SERVICE",
            "DOMAIN",
            "API",
            "REPOSITORY",
            "DTO",
        ]
        arch_real = False
    elif architecture_components:
        arch_items = list(architecture_components)
        arch_real = True
    else:
        arch_items = ["ARCHITECTURE AWAITING ANALYSIS"]
        arch_real = False

    arch_pill_cls = "mf-arch-real" if arch_real else ""
    arch_nodes = "".join(
        _node_svg(560, 20 + i * 30, 190, 24, item, f"mf-arch-pill {arch_pill_cls}", 0)
        for i, item in enumerate(arch_items[:6])
    )

    svg = f"""
    <div class="mf-diagram-wrap {boot_cls} {core_cls}">
      <div class="mf-diagram">
        <svg viewBox="0 0 780 260" xmlns="http://www.w3.org/2000/svg">
          {subsystem_nodes}
          {connectors}
          <circle class="mf-core-shell" cx="400" cy="150" r="46"/>
          <circle class="mf-core-pulse" cx="400" cy="150" r="46" fill="none"
                   stroke="currentColor" stroke-width="1" opacity="0.4"/>
          <text class="mf-core-label" x="400" y="146" text-anchor="middle">AI</text>
          <text class="mf-core-label" x="400" y="162" text-anchor="middle">CORE</text>
          <path class="mf-flow-line {flow_active}" d="M446,150 C 500,150 500,150 560,150"/>
          {arch_nodes}
        </svg>
      </div>
    </div>
    """
    st.markdown(svg, unsafe_allow_html=True)


def render_subsystem_nav(on_select: Callable[[str], None]) -> None:
    """The real, functional counterpart to the decorative SVG nodes above
    -- five buttons sharing the same labels, since Streamlit cannot route
    an SVG click back into Python without a custom component build."""
    cols = st.columns(len(SUBSYSTEMS))
    for col, sub in zip(cols, SUBSYSTEMS):
        with col:
            if st.button(sub.label, key=f"subsystem_{sub.key}", help=sub.description):
                on_select(sub.target_tab)
