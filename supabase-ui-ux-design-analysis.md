# Supabase UI/UX Design Analysis — the vibe, and what it means for Data Cleaner Studio

**Date:** 2026-11-06. **Purpose:** a UI/UX design analysis of supabase.com
(dashboard + marketing site), written to carry the same vibe and feelings
into the Data Cleaner Studio web app. This is the authoritative design brief
for the rebuild — it sits above the token list in
`supabase-design-study.md` and the full-site report in
`research_notes/supabase-website-full-analysis-20261106-1743/report.md`
(§6 design language, §8 UX patterns).

**Confidence:** the tokens and layout facts below were measured off the live
pages by browser tasks on 2026-11-06. The font-family names and the exact
hex values in the full report's §6 are secondary-sourced reconstructions
(the official brand page was not opened) — treat them as close, not gospel.
The *feelings* below are a synthesis of what was observed, not a quote.

## 1. The vibe in one paragraph

Supabase feels **calm, precise, and quietly confident** — a tool that gets
out of the way so the work can show. Nothing shouts. The page is almost
entirely black, white, and grey; a single green appears only where an
action lives or something succeeded, so every green pixel means
"something you can do" or "this worked". Space is generous, type is
small and exact, edges are hairlines instead of shadows, and motion is
functional, never decorative. The feeling is a well-lit workshop bench:
clean surface, sharp tools in a row, nothing extra. A developer trusts it
because it looks like it was built by people who care about the same
details the developer cares about.

## 2. The visual system (measured)

- **Background** `#fdfdfd` (near-white, never pure white glare). Cards
  `#ffffff`. Panels / inline code `#f8f8f8`–`#fafafa`.
- **Ink** `#030303` headings, `#4d4d4d`–`#484848` body, `#696969` muted.
- **Two greens, used differently:** brand green `#3ecf8e` (logo mark
  only); UI green `#0f7e4e` / `#117f50` (primary buttons, links, success).
  Primary button: subtle vertical gradient `#118050` → `#0e7d4e`, white
  text, ~8px radius, ~36px tall. Secondary: white, 1px `#e5e5e5` border,
  black text. Amber for warnings: fill `#f4ece3`, text `#f3ba63`/`#e69344`.
- **Borders, not shadows.** Hairlines `#e8e8e8` (buttons ~`#e4e4e4`).
  Cards flat, radius 10–12px; buttons/inputs 6px; pills fully rounded.
- **Typography:** clean neo-grotesque sans (Inter-like), tight heading
  tracking, H1 ~28px weight 500 (dashboard) / ~48px weight 500
  (marketing hero), body 13–14px, micro-labels uppercase 10–11px with
  wide letterspacing. **Monospace for numbers, prices, and code**
  (~13–14px). Code panels are WHITE with a hairline border and coloured
  syntax — not dark blocks.
- **Layout:** centred containers (homepage ~1100px, pricing ~1370px,
  docs ~1260px), section spacing 120–160px. Nav sticky 64px, solid
  `#fdfdfd`, translucent + backdrop blur on scroll. Sidebar: a 46px icon
  rail + ~260px secondary panel; active item a `#f3f3f3` pill with a dark
  left edge; hover `#f8f8f8`. Top bar ~48px: breadcrumb + green Connect
  button + Search (Ctrl K) pill.

## 3. The interaction language (how it moves and responds)

- **Motion is functional, never decorative.** No hero video, no autoplay,
  no scroll-jacking. What moves: tabs swap a screenshot or code example;
  a green spinner while loading; grey skeleton bars fading in; instant,
  subtle hovers; tooltips. That is the whole motion vocabulary.
- **Feedback is immediate and quiet.** Buttons darken slightly on hover.
  A toggle flips green. A copied key shows a small confirmation. Nothing
  bounces, nothing slides across the screen.
- **States are explicit and recoverable.** A paused project says so
  plainly, with a one-click Restore and a warning before it pauses. An
  empty table is an empty state with a next step, not a dead end. Errors
  name the cause and the fix.
- **One primary action per screen.** The green button is always the one
  thing to do next; everything else is white or grey. The closing line
  "Build in a weekend, scale to millions" repeats on every page — one
  message, everywhere.
- **Copy is plain and specific.** Short sentences, real numbers, the
  actual artefact shown (a typed table, a 5-line code call) instead of
  benefit adjectives. Docs start with "pick your framework", not with
  concepts.

## 4. What this means for Data Cleaner Studio — screen by screen

- **Login / sign up:** a calm gate, not a sales page. Centred column,
  near-white, logo + name + one-line tagline, email/password, the
  security check fitting neatly inside the column (no clipping), one
  dark-green Log in button. Nothing else competes with it.
- **Shell:** Studio-style sidebar (Upload, Clean, Analyse, Export,
  Profile, grouped under tiny uppercase labels), active item the
  `#f3f3f3` pill with the dark left edge. Slim top bar: breadcrumb-style
  title of the current screen + the file name when one is loaded.
- **Upload:** a clean drop zone, hairline border, one green "Choose file"
  button. The empty state is the product's first impression: a short
  line, a sample-data button, and nothing else.
- **Clean:** the operations as modular cards ("use one or all") — each
  card a small white box with a green line icon, a 16px title, one grey
  line of description. Applying one feels like ticking a precise tool
  off a bench, not running a wizard.
- **Tables:** dense, spreadsheet-like, hairline-ruled, white, monochrome
  except green actions. Numbers in monospace. Column types shown the
  way Supabase shows them (`name text`, `price numeric`) — the type is
  part of the table's honesty.
- **KPIs / charts:** small, exact numbers in monospace; charts on white
  (the current dark-background chart PNGs must go — they break the
  whole feeling). One green accent per chart at most.
- **Export:** one green primary action ("Download cleaned file"), the
  other formats as quiet white buttons beside it. After export, a small
  green confirmation, not a modal.
- **Profile:** the same shell — account card, display name, storage
  usage as a thin progress hairline, danger zone at the bottom with the
  amber/red used only there.
- **Empty states:** every screen that can be empty states it plainly and
  offers the next step ("No file loaded yet — drop one in, or try the
  sample"). Never a blank area, never a dead end.
- **Errors:** name the cause and the fix in one line, in plain words.
  No red walls, no stack traces in the UI.

## 5. What NOT to do (the anti-patterns)

- No neon green, no gradients except the subtle button gradient, no
  drop shadows, no dark code blocks, no hero video, no heavy animation.
- No competing primary buttons — one green action per screen.
- No cluttered sidebars, no badges everywhere, no marketing copy inside
  the working screens. The app is a workbench, not a landing page.
- No dark-mode chrome, no "premium" gold, no playful illustrations in
  the data views. The one place personality is allowed is the logo and
  the empty-state line — and only there.

## 6. The feeling, as a test

Before any screen ships, hold it against this sentence: *"A developer
opens it, sees exactly what to do next, and trusts it because nothing
is trying to impress them."* If a screen is trying to impress, it has
failed the brief. If it is quiet, exact, and the green only ever means
"do this" or "this worked", it has passed.
