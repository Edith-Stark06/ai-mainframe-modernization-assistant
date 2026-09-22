"""
Regression tests for "THE MODERNIZATION JOURNEY" section of the landing
page (``app/frontend/landing_template.py::LANDING_HTML``, rendered by
``app/frontend/landing.py::render_landing`` via
``streamlit.components.v1.html``).

These are plain string/content assertions against the actual template
constant the renderer uses -- not a rebuild of a separate, unused mockup.
They exist to stop the section from silently regressing back to either:

- the original three-unrelated-blocks composition (a small photo card, a
  vertical list of stage pills, and a stacked "table" of modern-application
  rows), or
- the first rebuild's rail-and-pill composition (``mj-rail``/``mj-stage``/
  ``mj-arrival``/``mj-token`` -- a horizontal stepper, still fundamentally
  static),

and to prove the current live SVG system (legacy sources -> intelligence
core -> analysis signals -> forming target architecture, plus two floating
live technical read-outs) is actually present in what gets rendered, with
its particle animations correctly gated so nothing sits visible at rest.
"""

from __future__ import annotations

from app.frontend.landing_template import LANDING_HTML, Z17_IMAGE_B64


def test_landing_html_is_wired_to_the_real_renderer():
    """``render_landing`` must actually use this exact template -- a
    passing test here that isn't reachable from the renderer would be
    worthless. See app/frontend/landing.py::render_landing."""
    import app.frontend.landing as landing_module
    import inspect

    source = inspect.getsource(landing_module.render_landing)
    assert "LANDING_HTML" in source
    assert "components.html" in source


def test_modernization_journey_section_present():
    assert '<section id="z17" class="z17-section">' in LANDING_HTML
    assert "THE MODERNIZATION JOURNEY" in LANDING_HTML
    assert "FROM MISSION-CRITICAL" in LANDING_HTML
    assert "TO MODERN APPLICATIONS." in LANDING_HTML


def test_mainframe_image_is_the_large_unbordered_source_visual():
    """The real IBM z17 image is the section's source visual -- large,
    blended into the page (no card/border), not a duplicate background
    image behind it."""
    assert "{Z17_IMAGE_B64}" in LANDING_HTML
    assert Z17_IMAGE_B64.startswith(
        '"""data:image/png;base64,'
    ) or Z17_IMAGE_B64.startswith("data:image/png;base64,")
    # exactly one live reference to the mainframe image in the transformation
    # canvas (as a CSS background-image), plus exactly one more in the
    # separate cinematic banner section -- never a second stacked image.
    assert LANDING_HTML.count("{Z17_IMAGE_B64}") == 2


def test_old_three_block_composition_is_fully_removed():
    """The pre-rebuild composition (tiny image card + vertical stage
    pills + stacked modern-application table rows) must not silently
    creep back in."""
    removed_classes = [
        "transform-visual",
        'class="t-left"',
        'class="t-center"',
        'class="t-right"',
        "t-label-group",
        'class="t-node"',
        'class="t-arrow"',
        "m-app-container",
        "m-app-header",
        "m-app-module",
        "data-flow-container",
        "data-flow-line",
        'class="data-particle"',
        "step-z17",
        "step-corridor",
        "step-modern",
    ]
    for cls in removed_classes:
        assert cls not in LANDING_HTML, f"old composition class {cls!r} reappeared"


def test_first_rebuild_rail_and_pill_composition_is_also_removed():
    """The first rebuild pass (a horizontal rail of numbered stage pills
    plus a stacked "arrival" table) was itself superseded by the live SVG
    system -- it must not silently creep back in either."""
    removed_classes = [
        "mj-rail",
        "mj-rail-track",
        "mj-stage-num",
        "mj-stage-name",
        "mj-stage-pill",
        "mj-arrival",
        "mj-mod-pair",
        "mj-annotations",
        "mj-token",
        "mj-particle",
    ]
    for cls in removed_classes:
        assert cls not in LANDING_HTML, f"first-rebuild class {cls!r} reappeared"


def test_single_continuous_canvas_structure():
    """The section is one canvas (stable mainframe source -> live SVG
    system), not disconnected blocks."""
    for marker in (
        'class="mj-canvas"',
        'id="mj-canvas"',
        'class="mj-source"',
        'id="mj-source"',
        'id="mj2-stage"',
        'id="mj2-svg"',
    ):
        assert marker in LANDING_HTML


def test_legacy_sources_stream_into_a_single_intelligence_core():
    """Five legacy sources (COBOL/JCL/DB2/CICS/VSAM) each get their own
    flow path and particles into one shared core -- not six independent,
    disconnected diagrams."""
    for source in ("COBOL", "JCL", "DB2", "CICS", "VSAM"):
        assert f">{source}<" in LANDING_HTML
    for i in range(1, 6):
        assert f'id="src-path-{i}"' in LANDING_HTML
    assert LANDING_HTML.count('class="mj2-flow-particle"') == 10  # two per source
    assert "MODERNIZATION" in LANDING_HTML
    assert "INTELLIGENCE" in LANDING_HTML
    assert 'class="mj2-ring r1"' in LANDING_HTML
    assert 'class="mj2-ring r2"' in LANDING_HTML
    assert 'class="mj2-ring r3"' in LANDING_HTML
    assert 'class="mj2-orbit-group"' in LANDING_HTML


def test_core_emits_signals_toward_analysis_labels():
    """The analysis outputs (AST/IR/CFG/Business Rules/Dependencies/Risk)
    are technical signal endpoints the core emits toward -- not static
    cards or a duplicated token list."""
    for token, path_id in (
        ("AST", "sig-path-ast"),
        ("IR", "sig-path-ir"),
        ("CFG", "sig-path-cfg"),
        ("BUSINESS RULES", "sig-path-rules"),
        ("DEPENDENCIES", "sig-path-deps"),
        ("RISK", "sig-path-risk"),
        ("ARCHITECTURE", "sig-path-arch"),
    ):
        assert f'id="{path_id}"' in LANDING_HTML
        assert token in LANDING_HTML
    assert LANDING_HTML.count('class="mj2-signal-particle"') == 7


def test_modern_application_is_a_connected_forming_diagram_not_a_table():
    z17_open = LANDING_HTML.index('<section id="z17"')
    banner_idx = LANDING_HTML.index('id="cinematic-banner"', z17_open)
    section_html = LANDING_HTML[z17_open:banner_idx]
    assert "<table" not in section_html
    assert "Java Services" in section_html
    assert "REST APIs" in section_html
    assert ">Data<" in section_html
    assert ">Validate<" in section_html
    # nodes are connected by drawn-in paths with travelling particles, not
    # laid out as static disconnected boxes
    for i in range(1, 6):
        assert f'id="arch-path-{i}"' in section_html
    assert LANDING_HTML.count('class="mj2-arch-particle"') == 5
    assert 'class="mj2-validate-ring"' in section_html


def test_one_hero_stream_traverses_the_full_pipeline():
    """A single primary data-stream particle travels source -> core ->
    architecture -> validate, tying the whole diagram together."""
    assert 'id="hero-path"' in LANDING_HTML
    assert 'class="mj2-hero-particle"' in LANDING_HTML


def test_live_hud_readouts_are_present():
    """The floating 'Business Rule Extracted' and 'Dependency Trace' live
    HUDs -- not static labels -- with real-looking sample content."""
    assert 'class="mj2-hud rule"' in LANDING_HTML
    assert "Business Rule Extracted" in LANDING_HTML
    assert "BR-001" in LANDING_HTML
    assert 'class="mj2-hud-typeline"' in LANDING_HTML
    assert "ELIGIBLE" in LANDING_HTML

    assert 'class="mj2-hud dep"' in LANDING_HTML
    assert "Dependency Trace" in LANDING_HTML
    assert "WS-AGE" in LANDING_HTML
    assert "0100-CALC-BENEFITS" in LANDING_HTML
    assert "DB2-MASTER" in LANDING_HTML


def test_cinematic_banner_is_a_separate_section_after_the_canvas():
    z17_open = LANDING_HTML.index('<section id="z17"')
    canvas_idx = LANDING_HTML.index('id="mj-canvas"')
    banner_idx = LANDING_HTML.index('id="cinematic-banner"')
    assert z17_open < canvas_idx < banner_idx
    assert "FROM LEGACY INFRASTRUCTURE" in LANDING_HTML
    assert "TO MODERN APPLICATIONS" in LANDING_HTML
    assert "CONCEPTUAL MODERNIZATION VIEW" in LANDING_HTML
    # the cinematic banner must never be mislabeled as the real product shot
    banner_section = LANDING_HTML[banner_idx : banner_idx + 400]
    assert "IBM z17" not in banner_section


def test_animations_are_paused_by_default_and_driven_by_a_live_class():
    """CSS keyframe animations (rings, core glow, signal-label pulses, HUD
    typewriter/result effects) start paused and only run once JS adds
    ``mj-live`` to the section root on scroll-entry -- the section must
    never auto-animate purely from CSS before the trigger fires."""
    assert "animation-play-state: paused" in LANDING_HTML
    assert "startLiveSystem" in LANDING_HTML
    assert "classList.add('mj-live')" in LANDING_HTML


def test_particles_never_appear_stuck_at_their_unanimated_origin():
    """Every travelling particle uses begin="indefinite" and is started
    explicitly via beginElement() -- and must stay hidden until that exact
    call fires, or every particle sits stacked and visible at its
    un-animated local (0,0) position, showing up as a stray dot at the
    SVG's origin. (Regression: this happened twice -- once with the
    particles permanently visible, once with a blanket `.mj-live` CSS rule
    revealing all of them together before their individual beginElement()
    calls had actually run.)"""
    assert 'begin="indefinite"' in LANDING_HTML
    assert "beginElement()" in LANDING_HTML
    for cls in (
        "mj2-flow-particle",
        "mj2-signal-particle",
        "mj2-arch-particle",
        "mj2-hero-particle",
    ):
        assert (
            f".{cls}" in LANDING_HTML.split("<section")[0]
            or f".{cls} {{" in LANDING_HTML
        )
    assert "visibility: hidden" in LANDING_HTML
    # visibility must be toggled per-particle inside the beginElement loop,
    # never by a single blanket class-based CSS rule (which would reveal
    # every particle together, before most had actually started moving)
    assert "particle.style.visibility = 'visible'" in LANDING_HTML
    assert ".mj-live .mj2-flow-particle" not in LANDING_HTML


def test_animation_respects_reduced_motion():
    assert "prefers-reduced-motion" in LANDING_HTML
    reduced_motion_blocks = [
        block
        for block in LANDING_HTML.split("@media (prefers-reduced-motion: reduce)")[1:]
    ]
    # under reduced motion, startLiveSystem() returns before ever adding
    # 'mj-live' or calling beginElement(), so particles simply stay at
    # their default `visibility: hidden` -- no separate reduced-motion
    # override is needed for them, but the diagram's other continuous
    # animations (rings, orbiting nodes, HUD typewriter/pulses) must be
    # explicitly stopped.
    assert any(".mj2-ring" in block for block in reduced_motion_blocks)
    assert any(".mj2-orbit-group" in block for block in reduced_motion_blocks)
    assert any(".mj2-hud-typeline" in block for block in reduced_motion_blocks)
    assert "if (reduceMotion) {" in LANDING_HTML


def test_no_build_marker_left_behind():
    """Guard against the mandatory build-verification markers accidentally
    shipping in the real template."""
    assert "MODERNIZATION_JOURNEY_BUILD_2026" not in LANDING_HTML
    assert "LIVE_MODERNIZATION_ANIMATION_BUILD_2026" not in LANDING_HTML
