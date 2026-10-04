# Dashboard design system

The Streamlit dashboard's look lives in `app/frontend/design/`. Views never
choose a colour, font or spacing; they compose primitives.

## Layout

| File | Role |
| --- | --- |
| `tokens.py` | The only place colour is defined. Light and dark `Palette`s, contrast maths, type and radius scales. |
| `streamlit_theme.py` | Renders `.streamlit/config.toml` from the tokens (`python -m app.frontend.design.streamlit_theme > .streamlit/config.toml`). A test fails if the file drifts. |
| `styles.py` | Builds the page stylesheet: `@font-face`, the `:root` token block for the active theme, `dashboard.css`, optional extras. |
| `dashboard.css`, `chat.css` | Component styles. Only `var(--c-*)` colours; a test rejects hex/`rgb()` literals and undefined tokens. |
| `ui.py` | Pure functions returning escaped, compact HTML: `badge`, `status_badge`, `page_header`, `callout`, `kpi_grid`, `stepper`, `stage_grid`, `finding`, `bar_chart`, `layer_diagram`, `empty_state`, `key_values`, `meter`, `breadcrumbs`, `brand`. |

The application frame is `app/frontend/shell.py` (sidebar, top bar, welcome),
data loading is `app/frontend/state.py`, and each page is a `*_view.py`.

## Rules

- **Colour is a token.** Add or change it in `tokens.py`; the CSS, the Streamlit
  config and both themes follow.
- **Contrast is tested.** Every text pair is >= 4.5:1 and every status mark
  >= 3:1, in both themes (`tests/frontend/test_design_tokens.py`).
- **Status is never colour alone.** A status is an icon plus a word. An unknown
  status is neutral, never green. "Ready" is claimed only for `PASS`.
- **Missing data is a dash or "unavailable", never zero.**
- **Escape everything.** Primitives escape their inputs; blocks are emitted on
  one line because Markdown turns blank lines and indentation into code blocks.
- **Charts** use one hue for unordered categories, thin bars, the value at the
  bar tip, and a visually hidden table with the same numbers.

## Visual language

Dark theme: deep navy surfaces (`#080c12` canvas, `#0d1117` cards) with a cyan
accent (`#2dd4e8`), the platform's original look. Light theme: a cool blue-grey
canvas with a deeper cyan-blue accent (`#0a6c86`) so white button text keeps
4.5:1. Serif display headings (Source Serif 4), Inter for UI, JetBrains Mono for
code. The theme follows the operating system (or Streamlit's Settings > Theme).
Fonts are bundled (`app/frontend/static/fonts`, served by Streamlit's static
serving) so the UI does not depend on a CDN.

## Assistant (chat)

A centred, single-column conversation: opening screen with one-tap questions,
right-aligned user bubbles, plain assistant text with numbered sources, and a
pinned rounded composer. Widget keys (`chat_input`,
`include_modernization_context`, `new_chat`, `suggest_0..3`) are stable.

## Accessibility audit

axe-core 4.10 (WCAG 2.0/2.1 A and AA) over the entry screen, welcome screen and
all eleven views, light and dark: no colour-contrast findings. Remaining
findings come from Streamlit's own markup and cannot be changed from Python:

- `aria-expanded` on the sidebar container (`aria-allowed-attr`).
- The scrollable code block in COBOL <-> Java is not keyboard focusable
  (`scrollable-region-focusable`).

Layouts reflow at 390px wide and at 200% zoom without horizontal scrolling.

## Adding a view

1. Put data loading in `state.py` (`ensure_*`), rendering in `<name>_view.py`.
2. Start with `section_header(title, subtitle, eyebrow=...)`.
3. Compose `ui` primitives; add a new primitive (with an escaping test) rather
   than writing inline HTML or inline styles.
4. Register the view in `shell.NAV_GROUPS`, `NAV_KEYS`, `NAV_ICONS` and the
   dispatch in `app.py`.
