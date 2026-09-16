# Phase 12 — UI Design Brief (not yet implemented)

**Status: design concept only.** Nothing in this document has been built.
It exists so the vision captured in conversation is not lost before
Phase 12 is formally scoped with its own Master Prompt (STEP 0 audit,
required tests, quality gates, git/PR workflow — the same discipline
every prior phase in this repo has followed).

This is a UX/visual brief, not an implementation plan. A future
Phase 12 Master Prompt should translate the sections below into
concrete deliverables, acceptance criteria, and out-of-scope boundaries
before any code is written.

## The one non-negotiable rule

> **The backend is truth. The animation is presentation.**

```
Backend
  ├── coverage
  ├── confidence
  ├── risks
  ├── dependencies
  ├── CFG
  ├── architecture
  ├── Java
  ├── compilation
  ├── tests
  └── behavioral validation
        │
        ▼
   UI visualization
```

Never the other direction. The UI must not invent a calculation, a
relationship, a confidence score, a readiness verdict, or a validation
result that the backend did not establish. This is the same principle
Phases 6–11 have enforced in code (`GroundedContext.validate()`,
"heuristic confidence" labeling, INCONCLUSIVE never silently upgraded
to PASS, etc.) — Phase 12 must enforce it visually. If the backend
reports `INCONCLUSIVE`, the UI shows `INCONCLUSIVE`, not a muted green
checkmark that reads as "basically fine."

## Product framing

Not a dashboard with 10 disconnected pages. A single **modernization
workspace** with a persistent central program context and progressively
richer views, navigated from a left rail:

```
┌──────────────────────────────────────────────────────────────┐
│ ◈ MODERNIZE     ELIGIBILITY.CBL      ● ANALYSIS COMPLETE     │
├──────────┬───────────────────────────────────────────────────┤
│ OVERVIEW │                                                   │
│ ARCH     │                 MAINFRAME CORE                    │
│ RULES    │              ◉  ELIGIBILITY                       │
│ DEPS     │             ╱│╲                                   │
│ FLOW     │            ╱ │ ╲   interactive visualization       │
│ COBOL ↔  │                                                   │
│  JAVA    │                                                   │
│ CHAT     │                                                   │
│ JAVA     │                                                   │
│ VALIDATE │                                                   │
│ REPORT   │                                                   │
└──────────┴───────────────────────────────────────────────────┘
```

The virtual mainframe / AI chip is the persistent visual identity of
the product, not a one-time splash animation — it doubles as live
navigation and as the system's status indicator throughout.

## Visual theme

Dark / near-black base: charcoal, graphite, a subtle grid, thin
circuit traces, glass-like panels, restrained cyan/teal illumination,
amber/red reserved for genuine warnings/failures, white typography.

Target feeling: **enterprise infrastructure control room** — a
mainframe terminal crossed with a spacecraft console. Explicitly *not*
a rainbow cyberpunk or gaming aesthetic.

## The opening sequence — virtual mainframe boot + AI transform

This is the intended "wow" moment, and it should be built as a real
state machine driven by actual pipeline events, not a fixed-length
video:

1. **Dark screen, terminal signals.**
   ```
   INITIALIZING LEGACY ENVIRONMENT...
   CONNECTING MAINFRAME...
   ```
2. **Mainframe boots.** A futuristic core appears; subsystems
   (`IDENTIFICATION`, `DATA`, `PROCEDURE`, `FILES`, `DEPENDENCIES`)
   illuminate one at a time — each light tied to a real Phase 1–5
   analysis stage actually completing, not a timer.
3. **AI chip activates**, locks onto the mainframe, a pulse travels
   through it as analysis runs. Completion reveals real counts (e.g.
   `70 DATA ITEMS · 21 PARAGRAPHS · 6 BUSINESS RULES · 63 DEPENDENCIES
   · 12 RISKS`) sourced from the actual `AnalysisBundle`.
4. **Transformation.** Glowing data streams lift out of the legacy
   core, pass through the AI chip, and reorganize into the generated
   Java architecture's real component types (`SERVICE`, `DOMAIN`,
   `DTO`, `REPOSITORY`, ...) — only after Phase 9 architecture
   generation has actually produced them.
5. **Transition into the workspace** (see layout above).

If a user skips or has seen the animation before, the workspace must
still be reachable directly with the mainframe/chip rendered in its
current (not "booting") state.

## The AI chip as a persistent, honest status indicator

The chip's state must be a direct, 1:1 rendering of backend state —
never decorative:

| Backend state | Chip |
|---|---|
| Analysis incomplete | dim |
| Analysis running | pulsing |
| Analysis complete | illuminated |
| Risks detected | warning state |
| Java generated | second layer illuminates |
| Compilation PASS | green validation pulse |
| Behavioral INCONCLUSIVE | amber |
| Behavioral FAIL | red |
| Fully behaviorally verified | complete illumination |

Example — a candidate that compiled and passed tests but could not be
behaviorally verified (the actual, honest state of this repo's own
environment today, since GnuCOBOL is unavailable) must render as:

```
╭────────────────────────╮
│      AI CORE            │
│   MODERNIZATION         │
│      CANDIDATE          │
│                         │
│  ✓ Analysis             │
│  ✓ Java Compile         │
│  ✓ Tests                │
│  ◐ Behavior             │
│                         │
│  INCONCLUSIVE            │
╰────────────────────────╯
```

Never a fully-green chip when compile+tests pass but behavior is
unverified — this is the same rule enforced in code by Phase 10/11
(`compile PASS + tests PASS + behavior FAIL/INCONCLUSIVE ⇒ candidate
remains invalid`).

## Per-screen concepts

Numbered per the PR/issue numbers under discussion for Phase 12
(`#132`–`#141`); a future Master Prompt should re-derive or renumber
these against whatever issue tracker is authoritative at kickoff time.

### #132 — Home / program selection

```
╔══════════════════════════════════════════════════════════════╗
║  ◈ MODERNIZE — AI-ASSISTED MAINFRAME MODERNIZATION            ║
║                                                                ║
║        ┌──────────────────────────┐                          ║
║        │       ◉ MAINFRAME        │                          ║
║        │       COBOL CORE         │                          ║
║        └──────────────────────────┘                          ║
║        SELECT PROGRAM TO BEGIN                                ║
║   [ ELIGIBILITY.CBL ]    [ CUSTOMER.CBL ]                    ║
╚══════════════════════════════════════════════════════════════╝
```

### Program overview

A hero panel (not a KPI grid) with counts and status sourced directly
from the backend `AnalysisBundle`/coverage/confidence/risk outputs —
no UI-side recalculation.

### #133 — Architecture view

An interactive graph of COBOL program → paragraphs → rules/data →
generated Java components, built only from real backend edges (Phase
1–5 dependencies + Phase 9 architecture). Clicking a node opens a
contextual panel with its type, source location, associated business
rules, confidence, and generated Java target. No UI-invented edges.

### #134 — Business rule explorer

Rules rendered as evidence cards (condition, action, source location,
severity) rather than table rows, each linking to source view and
dependency trace.

### #135 — Dependency explorer

An interactive dependency graph (variables → paragraphs → rules →
Java) with type filters (variables / paragraphs / files / external
calls / Java components), again backend-derived only.

### #136 — Control flow view

Renders the actual CFG — branches, entry/exit, and *visibly
distinguished unreachable nodes* — animated only along real CFG edges.

### #137 — COBOL ↔ Java trace (proposed hero feature)

Split-pane COBOL/Java source view with line-level highlighting driven
by real `SourceRef` mappings; a bottom panel surfaces the associated
business rule, confidence, and the actual Phase 10 behavioral
validation status (e.g. `⚠ BEHAVIORAL: INCONCLUSIVE`) for the selected
region — never omitted or glossed over.

### #138 — Grounded chat

Not a generic chat page — contextual to whatever the user has
currently selected (program / rule / component), and every answer
renders its evidence list and confidence band, directly surfacing
Phase 8's grounding contract instead of hiding it behind a chat
bubble.

### #139 — Java workspace

An engineering-workstation view: generated architecture summary,
generated file list, and explicit status rows for compilation, tests,
and behavior (including *why* behavior is inconclusive when it is) —
plus a repair-attempt count sourced from Phase 11's `QualityLoop`
audit log, not a generic "success" banner.

### #140 — Validation center (mission control)

The gate screen. Must show PARSER / ANALYSIS / COMPILATION / TESTS /
BEHAVIOR / RISKS / UNSUPPORTED as discrete, honestly-labeled rows.
Explicitly forbidden: a "✓ READY FOR MODERNIZATION" banner unless the
backend's own final status actually supports that conclusion — the
default correct rendering in this repo's current environment is
`◐ INCONCLUSIVE — Behavioral validation incomplete: COBOL runtime
unavailable`, not a green success state.

### #141 — Report export

An engineering "modernization dossier," not a generic PDF: program
overview, architecture, business rules, dependencies, risks, coverage,
confidence, strategy, generated Java, compilation, testing, behavioral
validation, and unresolved issues — with an explicit status section
that can legitimately read `INCONCLUSIVE`, generated purely from
backend analysis artifacts.

## Design rule to carry into the Phase 12 Master Prompt

When Phase 12 is actually scoped, its prompt should explicitly state
something equivalent to:

> Do not build a conventional dashboard. Build an interactive
> virtual-mainframe modernization workspace with a persistent central
> program context. The opening sequence boots a virtual mainframe,
> activates its subsystems, connects an AI modernization chip,
> visualizes analysis signals flowing through the system, and
> transforms extracted legacy structure into evidence-backed proposed
> Java architecture — every step gated on real backend events, never a
> fixed-duration animation. Every visual state (chip illumination,
> validation badges, readiness banners) must be a direct rendering of
> backend state and must never fabricate analysis, relationships,
> confidence, readiness, or validation.

Standard phase discipline still applies once Phase 12 is kicked off:
STEP 0 audit against the actual current `main`, required unit/e2e
tests, quality gates (black/ruff/mypy/diff --check), branch + PR
workflow, no auto-merge, and an explicit final-recommendation report —
consistent with how Phases 6–11 were each delivered in this repo.
