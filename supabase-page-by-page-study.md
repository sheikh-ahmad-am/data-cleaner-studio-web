# Supabase Dashboard — Page-by-Page Study (for the Data Cleaner Studio rebuild)

**Date:** 2026-11-07. **Purpose:** record exactly how the Supabase *dashboard*
(Studio) looks, page by page, so the Data Cleaner Studio web app can be
rebuilt to match it faithfully. This study exists because the user is right:
the earlier work studied the *tokens* (colours, radii, type) but never the
dashboard page by page — buttons, menus, tables, and the way each page is
put together were never written down.

**Sources (all local, no browser):**
- 12 dashboard screenshots the user sent 2026-11-07, 15:19–15:23 IST
  (`~/workspace/user/media_library/image/Screenshot_2026-11-07_151931.png`
  … `152352.png`). Every observation below is read off one of those frames;
  the file name is cited per page.
- `supabase-design-study.md` (2026-11-06, live dashboard + marketing site,
  hex sampled from pixels) and `supabase-ui-ux-design-analysis.md`
  (the vibe brief). Both are reused here only where they agree with the
  screenshots.
- `research_notes/supabase-website-full-analysis-20261106-1743/report.md`
  (marketing site + docs, text-fetch only — the dashboard itself was
  **not opened**: "sign-in required, out of scope") and
  `research_notes/supabase-ui-ux-analysis-20261106-1814/report.md`
  (marketing site; its §2.2 dashboard shell is explicitly **assembled
  from secondary sources, not directly rendered**). Neither report is used
  below as evidence for any dashboard fact.
- The app's current tokens: `ui_design.py` (`TOKENS` light, `DARK_TOKENS`).

**One thing to get straight first — theme.** The 2026-11-06 design study
sampled the dashboard in **light** mode (page `#fdfdfd`, cards `#ffffff`).
All 12 screenshots in this study are **dark** mode: near-black canvas,
white text, green accent. Supabase Studio is theme-aware (the account menu
offers System / Dark / Light), so both are real. The screenshots are the
dark render; hex values below are estimates read off dark renders, not
pixel-sampled gospel. Our app ships both themes, so the rebuild must carry
both — the dark side is the one the user is actually looking at.

---

## 0. The shared shell (present on every page)

Everything below is the frame every dashboard page sits in. If the rebuild
gets only one thing right, it is this frame.

**Top bar (~48px tall, dark, hairline bottom border).** Left to right:
- Supabase bolt logo (green lightning mark, ~20px) at the far left.
- Breadcrumb: org name "Ahm studio Org" + a **FREE** pill + chevron picker,
  then project name "data cleaning studio's Project" + chevron, then branch
  "main" + an amber **PRODUCTION** pill + chevron. Names are links; the
  chevrons open pickers.
- Right side: a green **Connect** pill button (plug icon + "Connect", white
  text on green, fully rounded, ~28px tall); a plain "Feedback" text link;
  a search pill — magnifier icon + "Search..." + "Ctrl K" hint, dark fill,
  fully rounded, ~28px tall; then four round icon-only buttons in a row
  (help `?`, lightbulb/Advisor, a square-with-arrow, a diamond/AI icon);
  finally the avatar — a white circle with a person outline — at the far
  right. Hovering the avatar shows a dark tooltip, "Account settings".
- No page title lives in the top bar. The top bar is chrome, not content.

**Far-left icon rail (~48–56px wide, same dark background).** Icons only,
one per dashboard section, vertically stacked, ~18px thin line icons
(Lucide-style, 1px stroke): home (top), table, SQL/terminal, database,
lock (Authentication), folder (Storage), Edge Functions, Compute,
Realtime, Advisors (lightbulb, with a small orange dot), Observability,
Logs, Integrations, and the gear (Project Settings) near the bottom.
The active icon sits in a rounded-square highlight. Every icon has a
hover tooltip ("Back to organization home", "Account settings", etc.).
This rail is the dashboard's first nav layer — it never shows labels.

**Secondary sidebar (~260px wide, same dark background, hairline right
edge).** This is the second nav layer: a section title at the top
("Project Overview", "SQL Editor", "Database", "Settings"), then nav
items as **icon + label rows** (~30px tall, ~13px text), grouped under
tiny uppercase section labels (DATABASE MANAGEMENT, ACCESS CONTROL,
CONFIGURATION, PLATFORM — 10–11px, wide letterspacing, muted grey).
The active item is a lighter pill background with semibold white text.
"NEW" appears as a small green mint pill on Compute and Pipelines;
"BETA" as a small amber pill on Vault. The sidebar is how you know where
you are — the rail alone does not say it.

**Content area.** Full remaining width, same dark canvas, no separate
grey background, no card wrapping the whole page. Pages are one long
scrolling column; section titles are large white headings (H1 ~28px,
weight ~500), section subheads ~20px, body 13–14px, muted text mid-grey.
Everything is flat: 1px hairline borders do the work, almost no drop
shadow anywhere. Green is rationed — brand mark, primary buttons,
success/status only. Numbers that matter (counts, sizes, metrics) are
set in monospace.

**Command palette.** `Ctrl K` / `Cmd+K` opens a global command menu
(navigation, docs search, AI actions). A keyboard-shortcut system exists
throughout: hovering SQL Editor shows a tooltip "Go to SQL Editor —
G then S". Our app has a search box labelled as the honest substitute;
there is no global key listener in Streamlit.

---

## 1. Project Overview (home) — top half

*Source: `Screenshot_2026-11-07_151931.png` (and 151942 / 151958 / 152010
/ 152101, same page with the sidebar open / tooltips / account menu).*

- **H1:** project name "data cleaning studio's Project", ~28px, white,
  weight ~500. Directly under it, the project URL in muted grey
  (`https://tembowfascqjqgtqumlw.supabase.co`) with a small dark **Copy**
  split-button beside it (label "Copy" + chevron segment).
- **Status tiles, left column — six tiles in two columns.** Each tile is:
  a ~48px square icon box (thin `#2e2e2e`-ish border, ~8px radius, dark
  fill) holding one line icon, beside an uppercase micro-label
  (STATUS, COMPUTE SIZE, GITHUB, RECENT BRANCH, LAST MIGRATION,
  LAST BACKUP — 10–11px, letterspaced, muted) and a value in white
  15–16px ("Healthy", "NANO" as a small dark pill, "No repository
  connected", "No branches", "No migrations", "No backups"). Icons:
  STATUS is a 3×3 grid of green dots; COMPUTE SIZE a chip; GITHUB the
  GitHub mark; RECENT BRANCH a branch icon; LAST MIGRATION / LAST BACKUP
  a database / archive icon. No card wraps the tiles — icon box +
  label + value, on the bare canvas.
- **Right: the diagram canvas.** A large dark panel (~half the page
  width) with a faint dotted grid (dots ~`#2a2a2a`), rounded corners
  (~12px), mostly empty. One floating node card sits inside it:
  "Primary Database" — a dark card (~1px border, ~10px radius) with a
  green database icon in a rounded green square at left, bold title
  "Primary Database", "South Asia (Mumbai)" and "ap-south-1 · Nano"
  below it in muted text, an India flag at the card's right edge, and a
  metric strip along the card's bottom: "CPU 2% · Disk 16% · RAM 57% ·
  12/60 conns" in small mono text with middle-dot separators. Two tiny
  icon buttons sit at the canvas's top-right corner (a diagram/layout
  toggle and a globe). The canvas is mostly empty space — the emptiness
  is the design; the node is the only thing on it.
- **What our app has of this:** the KPI-tile pattern (`kpi_tile` in
  `ui_design.py`: uppercase micro-label + large mono value) is the same
  idea, but our tiles are not the icon-box + label + value row Supabase
  uses, and we have no dotted-grid canvas and no floating node card.

## 2. Project Overview — lower half ("Get connected" + usage)

*Source: `Screenshot_2026-11-07_152130.png`.*

- **"Get connected" section.** H2 "Get connected" (~20px white) above
  one continuous strip of **six equal cards in a single row, separated
  by vertical hairlines, no gaps between them**: Framework ("Use a
  client library"), Server ("Build APIs"), Direct ("Connection
  string"), ORM ("Third-party library"), MCP ("Connect your agent"),
  API Keys ("Manage project keys"). Each card: a small line icon centred
  on top, a bold white title (~15px), a muted grey subtitle (~13px).
  The strip reads as one table with six cells, not six separate cards.
- **Stats strip.** "132 Total Requests" and "87.9% Success Rate" — big
  white number (~20px) + muted label, side by side, left-aligned.
  At the right, a dark pill dropdown "Last 60 minutes" with a chevron.
- **Metric cards (horizontally scrollable row, ">" arrow at the right
  edge to reveal more).** Four visible: API GATEWAY 75, STORAGE 31,
  POSTGRES 16, AUTH 10. Each card: dark fill, ~10px radius, 1px border.
  Top row: uppercase label (11px, muted) at left; at right, "WARNINGS"
  with an amber dot + count and "ERRORS" with a red dot + count.
  Large count (~28px white) below the label. Bottom: a vertical bar
  chart of thin green bars (amber/red segments where warnings/errors
  occurred) with a time axis ("Nov 7, 2:18pm" → "Nov 7, 3:18pm").
  Hovering a bar shows a dark tooltip ("Nov 7, 2:54pm / Infos 2").
  The POSTGRES card shows 3 red error bars — errors are visible in the
  chart itself, not hidden behind a badge.
- **"Advisor found no issues"** — plain white text, left, with an
  "Ask Assistant" button at the right (diamond/sparkle icon + label,
  dark pill with hairline border).
- **What our app has of this:** our Dashboard/KPIs pages have tiles and
  charts, but not this strip form: no six-cell "get connected" strip,
  no big-number + success-rate stats strip with a time-range dropdown,
  no per-service metric cards with warning/error dots and bar sparklines,
  no "Advisor found no issues" line with an Ask Assistant button.

## 3. SQL Editor

*Source: `Screenshot_2026-11-07_152154.png`.*

- **Left sub-sidebar (~260px).** Header "SQL Editor" (white, ~15px).
  A search box ("Search queries..." + chevron + a "+" square button).
  Collapsible groups, each a tiny uppercase label with a chevron:
  SHARED, FAVORITES, PRIVATE, LOGS. FAVORITES holds an empty-state
  card: "No favorite queries" (white) + "Save a query to favorites for
  easy accessibility by clicking the ♡ icon." (muted, centred).
  PRIVATE holds "No private queries created yet" + "Queries will be
  automatically saved once you start writing in the editor" + a list
  of saved queries (small SQL icon + name `dummy_query_1`…`4`, the
  active one highlighted with a dark left bar). Bottom: a full-width
  dark button "View running queries".
- **Main area.** A tab strip at the top ("+ New" tab). The editor
  itself is a large dark pane, line number "1" at the left gutter, and
  grey mono placeholder text: "Hit CTRL+SHIFT+K to generate query or
  just start typing". No line numbers column chrome, no minimap — just
  text on dark.
- **Toolbar (top-right of the editor).** Left to right: a "⋮" kebab
  icon button; a **Database** dropdown (database icon + label +
  chevron, dark pill); a **Save** button ("Save Ctrl S", dark pill,
  text + shortcut hint); a green **Run** button ("Run Ctrl ↵", white
  text on green, ~6px radius). The green Run is the one primary action
  on the screen.
- **Results area (below the editor).** Two tabs: "Results" (active —
  white text with a white underline) and "Chart" (muted). Body text:
  "Click Run to execute your query" — the word "Run" is itself a
  small dark pill, i.e. the instruction names the button by showing
  it. Empty state is a sentence, not a blank.
- **What our app has of this:** nothing equivalent. Our app has no
  editor page, no query list, no tab strip, no Run/Save toolbar, no
  Results/Chart tab pair. The closest pattern is our file-viewer /
  preview tables, which are Streamlit dataframes, not this layout.

## 4. Schema Visualizer (Database)

*Source: `Screenshot_2026-11-07_152226.png`.*

- **Left sub-sidebar.** Header "Database". Groups: DATABASE MANAGEMENT
  (Schema Visualizer — active pill; Tables; Functions; Triggers;
  Enumerated Types; Extensions; Indexes; Publications), ACCESS CONTROL
  (Policies; Roles), CONFIGURATION (Settings), PLATFORM (Pipelines with
  a green NEW pill; Backups; Migrations). This is the deepest nav in
  the screenshots — four groups, 17 items.
- **Toolbar.** "schema public" dropdown at left, "Find table..." search
  input beside it. At the right: a **Copy as SQL** split-button (copy
  icon + label + chevron) and an **Auto layout** button (dark pill).
- **Canvas.** Dotted grid (same as Overview). Table nodes are dark
  cards (~1px border, ~8px radius): header row with a table icon +
  table name (white, semibold) + a "⋮" kebab at the right; then one
  row per column — a small key icon for primary keys, a diamond for
  nullable/non-nullable, the column name at left (white), the type at
  right in muted mono (`uuid`, `text`, `timestamptz`, `int4`, `bool`).
  Thin connector lines join related columns across cards
  (`profiles.id` → `sessions.user_id` → `auth.users.id`), with the
  target shown as a small dark pill ("auth.users.id"). Bottom-right: a
  minimap — a white card holding black rectangles that mirror the
  canvas layout. Bottom legend, centred: key/identity/unique/nullable/
  non-nullable icons with labels ("Primary key", "Identity", "Unique",
  "Nullable", "Non-Nullable").
- **What our app has of this:** our Schema-adjacent views are the
  Preview/Clean tables (Streamlit dataframes with column names + types
  shown as `name text` — that part matches Supabase's honesty about
  types). We have no diagram canvas, no node cards, no connector
  lines, no minimap, no legend.

## 5. Database Tables

*Source: `Screenshot_2026-11-07_152238.png`.*

- **H1 "Database Tables" (~28px white).** Toolbar below it: "schema
  public" dropdown, "Search for a table" input, "Entity Type"
  dropdown — all dark pills/inputs in a row at the left. At the right,
  a green **+ New table** pill button (plus icon + label, white text
  on green).
- **The table itself.** One bordered dark panel (~10px radius) holding
  the rows. Header row: uppercase micro labels (NAME, COLUMNS,
  ROWS (ESTIMATED), SIZE (ESTIMATED), REALTIME — 11px, muted,
  letterspaced) with a hairline underneath. Rows ~48px tall, separated
  by hairlines: a table icon + name in white semibold (`email_login_codes`,
  `profiles`, `sessions`); counts in plain white text (8 / 6 / 48 kB);
  REALTIME shows "✕ Disabled" (muted, with a small ✕); at the row's
  right end, a dark pill button **"View columns"** and a "⋮" kebab
  button. Footer inside the panel: "3 tables" (muted, small).
  Nothing else on the page — the table is the page.
- **Row treatment:** the name column is the only semibold text; numbers
  are plain; the only buttons in a row are at its far right. No
  checkbox column, no coloured status in this list (realtime is the
  only status, and it is text, not a badge).
- **What our app has of this:** our data tables are Streamlit
  dataframes — they do not have this header style (uppercase micro
  labels), the per-row "View columns" pill + kebab, the "N tables"
  footer, or the toolbar trio (schema dropdown + search + entity-type
  dropdown + green New button). The closest we get is the Preview
  table with column types shown.

## 6. Database Functions

*Source: `Screenshot_2026-11-07_152253.png`.*

- **H1 "Database Functions" (~28px white).** At the right, a **Docs**
  button (book icon + "Docs", dark pill with hairline border).
- **Toolbar.** "schema public" dropdown, "Search for a function"
  input, "Return Type" dropdown, "Security" dropdown — dark pills in
  a row. At the right, a green **+ New function** pill button (plus
  icon + label) and a small diamond icon button beside it.
- **The table.** Same bordered dark panel as Tables. Header row:
  NAME, TYPE, ARGUMENTS, RETURN TYPE, SECURITY (uppercase micro).
  Rows ~48px, hairline-separated: the function name as an **underlined
  white link** (`app_create_session`, `app_delete_account_data`,
  `app_get_profile` … — underline is the affordance, not colour);
  TYPE is plain "Function"; ARGUMENTS is muted mono, truncated with
  "…" (`p_token text, p_user_id uui…`); RETURN TYPE is plain
  (`void`, `jsonb`, `text`, `TABLE(created_at timesta…`); SECURITY is
  plain "Definer"; a "⋮" kebab at the far right of every row.
- **What our app has of this:** no equivalent page at all. The
  functions list is a Supabase-internal view; our app has no page
  that lists named operations this way. The pattern worth stealing is
  the table itself: underlined name-as-link, mono truncated arguments,
  kebab per row.

## 7. Project Settings — General

*Source: `Screenshot_2026-11-07_152352.png`.*

- **Left sub-sidebar.** Header "Settings". Groups: CONFIGURATION
  (General — active pill; Infrastructure; Integrations; API Keys;
  JWT Keys; Log Drains; Add-ons), INTEGRATIONS (Data API ↗, Vault
  with amber BETA pill ↗), BILLING (Subscription ↗, Usage ↗). The ↗
  marks items that open elsewhere; the active item is a plain pill.
- **Main.** H1 "Project Settings" + a one-line subtitle in muted grey:
  "General configuration, domains, ownership, and lifecycle".
- **"General settings" section.** H2 (~20px white). Below it, one
  bordered dark card. Inside the card, rows separated by hairlines;
  each row: a bold white label ("Project name") + a muted description
  under it ("Displayed throughout the dashboard."), and at the right
  a dark input holding the value ("data cleaning studio's Project")
  or, for IDs, the value + a **Copy** button (copy icon + "Copy",
  dark pill) inside the input's right end. "Project ID" and "Project
  region" rows follow the same shape. At the card's bottom-right, a
  green **Save changes** button (dimmed/disabled-looking until
  something changes — green fill, white text, ~6px radius).
- **"Project access" section.** H2, then a bordered card: a row
  "Organization-wide access" (bold) + "All 1 organization members can
  access this project." (muted) + a **Manage members** button (dark
  pill) at the right; below, a mini-table with header MEMBER / ROLE
  (uppercase micro) and a row: email + a "YOU" pill + "Owner".
- **What our app has of this:** our Profile page has the same *shape*
  (title, caption, sections separated by hairlines, a danger zone at
  the bottom) and our Settings page exists, but the Supabase form-row
  pattern — label + description on the left, input-with-copy-button on
  the right, one bordered card per section, Save at the card's
  bottom-right — is not what our Profile/Settings pages do. Ours stack
  label above input; Supabase puts them side by side in a row.

## 8. The account menu

*Source: `Screenshot_2026-11-07_152035.png` (menu open) and
`152010.png` (avatar hover tooltip "Account settings").*

- Trigger: the white avatar circle at the top bar's far right. Hover
  shows a dark tooltip, "Account settings". Click opens a dropdown
  panel (~300px wide) below-right of the avatar: dark card, 1px
  border, ~8px radius, no shadow to speak of.
- Contents, top to bottom: the email in bold white
  ("ahmadfed966@gmail.com"); a row with a person icon + "Account";
  a row with a flask icon + "Feature previews"; a row with a list
  icon + "Changelog"; a hairline divider; a muted section label
  "Theme"; three rows — "System", "Dark" (selected: a filled dot at
  the row's left + a lighter row background), "Light"; a hairline
  divider; a row "Timezone" with "Auto (Asia/Calcutta)" in muted text
  and a ">" chevron at the right; a hairline divider; a **full-width
  green "Upgrade to Pro" button** (white text, ~6px radius); a final
  row, "Sign out", in plain white text.
- Every row is icon + label (or label + value + chevron). Nothing in
  the menu is a bare text link; nothing has a coloured background
  except the selected theme row and the green Upgrade button.
- **What our app has of this:** our avatar menu (green circle with the
  user's initial, in the *sidebar*, not the top bar) opens a popover
  with the email as a caption, Profile, a theme switch, Log out, and
  hairline dividers. That is the same skeleton, but: ours has no icons
  on the rows, no System/Dark/Light three-way choice (ours is a
  two-way toggle), no Timezone row, no Upgrade button (correct — we
  have no paid tier), and it lives in the sidebar because Streamlit
  has no top bar to put it in. Note also: in the live check the theme
  switch inside our menu was not visible — the code builds it, but it
  did not render on screen.

## 9. The sidebar nav — states

*Sources: `151942.png`, `151958.png` (sidebar open over the overview),
`152226.png`, `152238.png`, `152253.png`, `152352.png` (Database /
Settings sub-sidebars).*

- Two layers, always: icon rail (icons only) + secondary sidebar
  (icon + label rows under uppercase group labels).
- Active item: lighter pill background + semibold white text. In the
  project-level sidebar the active item ("Project Overview") is a
  filled pill; in the Database sub-sidebar the active item ("Schema
  Visualizer", "Tables", "Functions", "General") is the same pill.
- Hover: a very subtle wash on the row, plus a dark tooltip. The
  tooltip for a nav item can carry a keyboard hint ("Go to SQL Editor
  — G then S"). The tooltip is the nav's affordance for shortcuts;
  the shortcut itself is a power-user feature, not the primary way in.
- The gear (Project Settings) sits at the bottom of the icon rail,
  separated from the rest — settings are always one click away, but
  visually apart from the working sections.
- **What our app has of this:** one layer only — a Streamlit sidebar
  with grouped text rows (DATA / ANALYSE / OUTPUT / WORKSPACE),
  active pill, hover wash, and `title` tooltips. There is no icon
  rail, no icons on the nav rows, no gear pinned to the bottom, and
  the nav is display-only (the real selection control is a radio
  further down the sidebar).

---

## 10. The button + icon system — the "button logo" answer

The user said: *"there is no button logo."* He is right, and this is the
single most visible missing piece. Here is exactly what Supabase does:

- **Every action button carries a small line icon immediately to the
  left of its text label.** The icon is a thin-stroke (Lucide-style)
  outline glyph, ~16px, same colour as the label, ~6px gap to the text.
  Observed: Connect (plug icon + "Connect"), New table (plus +
  "New table"), New function (plus + "New function"), Docs (book icon
  + "Docs"), Ask Assistant (sparkle/diamond icon + "Ask Assistant"),
  Copy (copy icon + "Copy"), Copy as SQL (copy icon + "Copy as SQL"),
  Auto layout (no icon visible — text only), Manage members (text
  only), Save changes (text only), View columns (text only),
  Upgrade to Pro (text only, full-width green). So: primary creation
  actions and the top-bar actions always have an icon; secondary
  per-row buttons ("View columns", "Manage members", "Save changes")
  are often text-only.
- **Icon-only buttons** are the other half of the system: the top bar's
  round buttons (help, Advisor, SQL, AI), the "⋮" kebab per table row,
  the "+" in the SQL Editor search box, the ">" chevron in the metric
  cards, the collapse chevrons on sidebar groups. Every one of them
  shows a dark tooltip on hover naming what it does (and the shortcut
  where one exists). An icon-only button without a tooltip does not
  exist in this dashboard.
- **The Supabase logo itself (the green bolt) appears exactly once in
  the chrome: at the far left of the top bar.** It never appears on a
  button. What the user is missing is not the logo on buttons — it is
  the *icon* on buttons. Every button that does something has a small
  picture at its left; ours have only words.
- **Button anatomy (dark render):**
  - Primary: green fill (bright green in dark mode, ~`#1f9d63`, white
    text), fully rounded pill for top-bar/creation actions
    ("Connect", "New table", "New function", "Run"), ~28px tall,
    13–14px medium label, icon 16px at left. "Save changes" is the
    exception — same green, but ~6px radius, not a pill.
  - Secondary: transparent/dark fill, 1px hairline border
    (~`#2e2e2e` in dark), white text, 6px radius ("Save", "Docs",
    "Copy", "View columns", "Ask Assistant", "Manage members").
  - Split buttons: "Copy" and "Copy as SQL" are split — label on the
    left, chevron segment on the right, one shared border.
  - Destructive: no red button is visible in these screenshots; the
    danger zone pattern (from the earlier study) keeps red to text/links
    only.
  - Disabled: "Save changes" renders dimmed (dark green, muted text)
    until a field changes.
- **What our app has of this:** essentially none of the icon half.
  `ui_design.py` already notes it in a code comment (line ~251):
  Streamlit buttons cannot carry a custom class, and the 93
  `st.button` / `st.download_button` / `st.link_button` calls across
  `app.py` and `feat_*.py` are all text-only — a grep for `icon=`
  finds nothing (the only icon in the app is the favicon). Our tokens
  already match the button *colours and radii* (primary `#117f50`
  with a `#118050 → #0e7d4e` gradient, secondary white + `#e5e5e5`
  border, 6px radius, hover washes) — the shape is right, the icon
  is missing. The honest fix is custom HTML buttons (or icon +
  label composed in markdown) for the primary actions, because
  `st.button` has no icon slot. That is a build decision, not a CSS
  tweak.

---

## 11. Mapping — Supabase pattern → our app

Our pages: Preview, Clean, Join, KPIs, Dashboard, Compare, Report,
Tools, How to use, Settings, Profile, Status. Status key: **has** /
**partial** / **missing**. "Partial" means the shape exists but a named
element is absent; "missing" means the pattern is not in the app at all.

| Supabase pattern | Maps to our page | Status | Note |
|---|---|---|---|
| Top bar (48px): logo + breadcrumb + Connect + Feedback + Search Ctrl K + round icon buttons + avatar | Shell (all pages) | **partial** | We have a 48px topbar (`topbar()`): breadcrumb + title only. No logo in the bar, no Connect, no Feedback, no Search pill, no round icon buttons, no avatar in the bar. The avatar lives in the sidebar instead. |
| Icon rail (icons only, tooltips) | Shell | **missing** | Streamlit has no second nav layer. Our sidebar is one layer of text rows. |
| Secondary sidebar: icon + label rows, uppercase group labels, active pill, NEW/BETA pills | Shell (sidebar) | **partial** | Group labels (DATA / ANALYSE / OUTPUT / WORKSPACE), active pill, hover wash, `title` tooltips: has. Icons on rows: missing. NEW/BETA pills: missing. Gear pinned at bottom: missing. |
| Project name H1 + URL + Copy split-button | Preview (header) | **partial** | We have the page title + tagline, no URL row and no Copy split-button. (Our app has no public URL per user to copy.) |
| Status tiles: icon box + micro-label + value | Dashboard / Status | **partial** | `kpi_tile` (micro-label + large mono value) exists, but without the 48px icon box at the left, and our tiles are cards, not bare rows. Status page has the status pill, not the six-tile grid. |
| Dotted-grid canvas + floating node card | Dashboard | **missing** | No dotted canvas, no floating node card. |
| "Get connected" six-cell strip | Preview / How to use | **missing** | No six-cell strip. The closest is the "What's inside" lines on the login screen. |
| Stats strip (big number + success rate + time-range dropdown) | Dashboard / KPIs | **partial** | We have KPI numbers and charts; no big-number + success-rate strip with a "Last 60 minutes" style dropdown. |
| Metric cards (label + count + warnings/errors dots + bar sparkline + hover tooltip) | Dashboard / KPIs | **partial** | We have charts on white and KPI tiles; no per-service cards with warning/error dots and bar sparklines. |
| "Advisor found no issues" + Ask Assistant | Status | **partial** | Status page has the health pill; no Advisor line and no Ask Assistant button. |
| SQL Editor (query list + tabs + editor + Run/Save + Results/Chart) | — (no equivalent page) | **missing** | No editor page at all. |
| Schema Visualizer (node cards + connectors + minimap + legend) | Clean / Preview (table view) | **partial** | Column names + types shown (`name text`) matches Supabase's type honesty. No diagram, nodes, connectors, minimap, legend. |
| Tables list (toolbar + table + View columns + kebab + "N tables") | Preview / Clean (data tables) | **partial** | Toolbar trio (schema dropdown + search + entity filter) and the green New button are missing; rows lack the per-row "View columns" pill + kebab and the "N tables" footer. Our tables are Streamlit dataframes. |
| Functions list (underlined name link + mono args + kebab) | — (no equivalent page) | **missing** | No page lists named operations this way. |
| Settings form rows (label + desc left, input + Copy right, one card per section, Save bottom-right) | Settings / Profile | **partial** | Profile has the same shape (title, caption, sections, hairline dividers, danger zone) and Settings exists, but our forms stack label above input; Supabase puts label + description left and input right in one row, inside one bordered card, with Save at the card's bottom-right. |
| Account menu (email + icon rows + Theme System/Dark/Light + Timezone + Upgrade + Sign out) | Shell (avatar menu) | **partial** | Same skeleton (email, Profile, theme, Log out, dividers) in the sidebar popover — but no icons on rows, two-way theme toggle instead of System/Dark/Light, no Timezone row, no Upgrade (correct — no paid tier). Live check: the theme switch inside the menu did not render. |
| Buttons with a left icon (the "button logo") | All pages | **missing** | All 93 app buttons are text-only. Tokens (colour, radius) match; the icon is absent everywhere. |
| Icon-only buttons with tooltips | All pages | **partial** | `title` tooltips exist on nav rows; kebab/icon-only buttons with tooltips do not exist in the app. |
| Command palette (Ctrl K) + keyboard shortcuts | Shell (Quick jump) | **partial** | Quick jump search box is the honest substitute; no global key listener exists in Streamlit, so no Cmd+K and no "G then S" hints. |
| Empty states (sentence + next step) | Preview / Clean / SQL-equivalents | **has** | "No recent files yet…" / "No file loaded yet" pattern matches Supabase's empty-state sentences. |
| Tables: uppercase micro headers, hairline rows, mono types | Preview / Clean | **partial** | Column types are shown; the table chrome (micro headers, per-row actions, footer) is Streamlit's, not Supabase's. |
| Danger zone (separated, red text only) | Profile | **has** | Present, separated by its own divider, red text only. |
| Green spinner + skeleton loading | All pages | **has** | Branded loader (bars + checkmark) + skeletons, per the loading-motion pass. |
| Theme System/Dark/Light | Shell | **partial** | Light + dark exist and are WCAG-AA checked; no "System" (follow OS) option. |

---

## 12. Dashboard pages NOT covered by these screenshots

These exist in the sidebar nav (visible in `151942.png`) but no screenshot
shows the page itself, so they are **unstudied** — nothing in this file
describes how they look:

- **Table Editor — data grid.** The earlier design study *did* cover the
  profiles grid (dense spreadsheet grid, tab strip, Filter/Sort/Insert
  toolbar, footer pagination), so this one is covered elsewhere, not
  here. Treat the earlier study as the source for it.
- **Authentication — Users.** Also covered by the earlier design study
  (filter bar, users table, provider pills, "Total: 10 users
  (estimated)"). Covered elsewhere, not here.
- **Storage — buckets / files.** Not covered anywhere. Unknown: bucket
  list, file grid, upload button, breadcrumbs, preview pane.
- **Edge Functions — list / detail / logs.** Not covered anywhere.
- **Compute.** Not covered anywhere (sidebar shows it with a NEW pill).
- **Realtime.** Not covered anywhere.
- **Advisors** (the "Advisor found no issues" page behind the Overview
  line). Not covered anywhere.
- **Observability.** Not covered anywhere.
- **Logs** (log explorer, filters). Not covered anywhere.
- **Integrations.** Not covered anywhere.
- **Authentication sub-pages** beyond Users: Providers, Email Templates,
  URL Configuration, Policies, Passkeys, OAuth Server, Auth Hooks —
  visible as nav items in the earlier study only by name. Not covered.
- **Database sub-pages** beyond Tables/Functions/Schema Visualizer:
  Triggers, Enumerated Types, Extensions, Indexes, Publications,
  Policies, Roles, Settings. Not covered.
- **Project Settings sub-pages** beyond General: Infrastructure,
  Integrations, API Keys, JWT Keys, Log Drains, Add-ons, Data API,
  Vault, Subscription, Usage. Not covered.
- **Organisation home** (the page behind the home icon / "Back to
  organization home" tooltip). Not covered.
- **Table Editor — row detail / edit forms** (insert row dialog, edit
  cell, RLS policy editor). Not covered.

---

## 13. Biggest gaps, ranked (what the rebuild must fix first)

1. **Buttons have no icons — the "button logo".** Every Supabase action
   button carries a 16px line icon left of its label; ours carry none.
   This is the first thing the eye notices and the thing the user named.
   Fix: custom HTML icon + label buttons for the primary actions
   (Connect-equivalent, New/Run/Save, Docs, Ask Assistant); `st.button`
   cannot do it.
2. **No icon rail, no icons on nav rows.** The dashboard's first nav
   layer is an icon rail with tooltips; our sidebar is text rows only.
   A rail is not native to Streamlit, but icon + label nav rows are
   achievable with custom HTML.
3. **No top bar worthy of the name.** Ours is breadcrumb + title. The
   dashboard's is logo + breadcrumb + green Connect + Feedback +
   Search (Ctrl K) + round icon buttons + avatar. The avatar belongs
   in the top bar, not the sidebar.
4. **Settings/Profile forms stack label above input.** Supabase puts
   label + description left, input (+ Copy) right, inside one bordered
   card per section, Save at the card's bottom-right. Ours stack.
5. **No "Get connected" strip, no metric cards with warning/error dots
   and sparklines, no Advisor line.** Our Dashboard shows KPIs and
   charts but not these three Overview patterns.
6. **Tables are Streamlit's, not Supabase's.** No uppercase micro
   headers, no per-row "View columns" pill + kebab, no "N tables"
   footer, no toolbar trio (schema + search + filter + green New).
7. **The two live-check failures from 2026-11-07 are still open:**
   the theme switch inside the avatar menu does not render, and the
   Profile caption ("Your account, sign-in and data.") does not show
   — both exist in code (`ui_design.py` `render_sidebar_avatar`,
   `feat_profile.py:155`) but not on screen. Any rebuild must verify
   these two on the live app, not just in tests.
8. **Profile page layout.** The live check found very large blank gaps
   between sections and Preview content sitting above Profile on the
   same long page. Supabase's settings pages are one tight column per
   section with no stray content above.

---

## Appendix — Live dashboard walk (2026-11-07, read-only, browser task)

Walked the live dashboard for this project (tembowfascqjqgtqumlw, "Ahm studio Org") 16:28–16:31 IST. Nothing was changed, no SQL was run, nothing was created or deleted. This appendix records the pages the screenshots did not cover, and confirms or corrects the screenshot findings. Theme observed: LIGHT.

### Global shell (all pages)
- **Top bar:** left, org avatar square (letter "A") + project selector "data cleaning studio's Project" with a "main" branch label (orange/brown) below it and a chevron; centre/right, a small pill control, a "Search project" field, two icon-only circular buttons, then a solid dark-green pill **Connect** (white text, plug/link icon), a small icon button, then the top-right circular avatar (black circle, white person icon) and a light-grey circular icon button beside it. No large Supabase wordmark in the dashboard header; the small Supabase logo mark sits at the top of the left navigation.
- **Left sidebar:** on first load a narrow **icon-only rail (~60 px)** — icons only, no labels: Project Overview, Table Editor, SQL Editor, Database, Authentication, Storage, Edge Functions, Realtime, Logs, Settings at the bottom. After clicking into a section it expands to a labelled sidebar (~260 px) with icons + text labels; the active item has a pale light-grey background and dark text. Some sections (Database, Authentication, Storage, Settings) add a second, narrower **sub-sidebar** to the right with its own section headings ("DATABASE MANAGEMENT", "CONFIGURATION") and the active sub-item in pale grey.
- **Floating toolbar:** a small white pill, centred at the bottom of the screen on most pages, with 5 grey icons: magnifier (search), clock/history, light-bulb, image, diamond/AI. It floats over content.
- **Bottom-left status toast** on most pages: a small white card listing "Database Healthy / View logs", "PostgREST Healthy / View logs", etc., with green tick icons.
- **Hover (live, not inferred):** hovering the Table Editor "Insert row" button produced NO visible colour/text change — only the pointer cursor. Sidebar items and table rows are the reactive elements (pale-grey hover/active background, table names as links, chevron/arrow buttons expand rows). No other hover animation was observed. (Our app's hover wash is therefore MORE reactive than Supabase's, not less — the soul pass's subtle hover is not the gap; the missing icons are.)

### Project Overview
- Title: large heading "data cleaning studio's Project"; beneath it the URL `https://tembowfascqjqgtqumlw.supabase.co` and a small white **Copy** button with a chevron (opens Copy project URL and API keys).
- **Status strip:** six white rounded cards in a grid — STATUS "Healthy" (green dot-grid icon; click opens a popover listing Database, PostgREST, Auth, Realtime, Storage, Edge Functions, each "Healthy" with a green check), COMPUTE SIZE "NANO" (chip icon, "NANO" in a grey pill outline), GITHUB "No repository connected", RECENT BRANCH "No branches", LAST MIGRATION "No migrations", LAST BACKUP "No backups".
- **Infrastructure:** a dotted-grid canvas with a white card "Primary Database — South Asia (Mumbai)", "ap-south-1 · Nano", and a link "CPU 2% · Disk 16% · RAM 56% · 8/60 conns". Top-right two small toggle buttons: "Show infrastructure as a diagram" (pressed/active, pale) and "Show infrastructure on the map", both icon-only, with a tooltip button "How does infrastructure work?" above them.
- **"Get connected":** six white cards/buttons in a row, each with a small icon and two lines of text: "Framework — Use a client library", "Server — Build APIs", "Direct — Connection string", "ORM — Third-party library", "MCP — Connect your agent", "API Keys — Manage project keys".
- **Reports strip:** "147 Total Requests" and "86.4% Success Rate" (live figures — minutes earlier they read 134 and 85.1%), with a white "Last 60 minutes" dropdown at right and a "Scroll right" arrow. Below, horizontally scrolling white service cards, each with a heading that is also a link, a large number, and "WARNINGS / ERRORS" counts, dated "Nov 7, 3:30pm – Nov 7, 4:30pm": API GATEWAY 86, 11 warnings, 0 errors; STORAGE 33, 5 warnings, 0 errors; AUTH 14, 4 warnings, 0 errors; POSTGRES 13, 0 warnings, 0 errors; REALTIME 1, 0 warnings, 0 errors; EDGE FUNCTIONS 0, 0 warnings, 0 errors.
- **Advisor:** "Advisor found no issues" (heading, text "No security or performance issues found") with a white "Ask Assistant" button; then "Reports" with a white "Add block" dropdown, and an empty card "Build a custom report — Keep track of your most important metrics" with a white "Add your first block" dropdown. Each section has a small "Drag to reorder section" grip button at its right edge.

### Table Editor (profiles table)
- Sidebar expands: "Tables" heading, small white database picker "public" with chevron, a "Search tables" field, Inferred schemas "public" with chevron, then the table list with a small table icon and name; the active row "profiles" has a pale-grey background. Below: "Relationships" (closed), "Views" (closed).
- Header: a tab strip with tabs "profiles" and "sessions" (each with a small grid icon and a close ×; "profiles" is the active tab, pale background), and to its right a blocker row with a "No RLS" button (white, shield icon) and icon-only buttons (new-window, pin, grey X "Close schema"). Below that, "Table Editor" as a small heading.
- Toolbar (white buttons, grey icons, left to right): **Insert row** — solid dark-green button (the only green one, rectangular, rounded corners, no icon); "Filter", "Sort", "Insert column" (with a small "Beta" pill), "Edit table", "Delete table", and an icon-only more button.
- Data grid: white, thin light-grey grid lines, grey column headers "id, email, display_name, created_at"; cells use a monospace-ish font; UUIDs and timestamps shown in full. "display_name" header shows "text"/"varchar" and a nullable marker; empty cells show "NULL" in grey at the upper-left of the cell.
- Contents: 2 records ("2 records", "Showing 1-2 of 2" bottom left; "100 / page" dropdown bottom right, page "< 1 >" with grey arrows). Row 1: id starting e77f9a…, email starting hamza…@gmail.com, display_name NULL, created_at 2026-11-06 12:57:41 GST. Row 2: id starting 26ef389…, email starting ahmad…@gmail.com, display_name NULL, created_at 2026-11-06 11:06:51 GST. Leftmost row header is a number (1 / 2).
- A bottom-right promo banner (dark teal/blue card) appeared over the grid ("Build fast. Ship faster. — Deploy Postgres with Supabase, on your own cloud", white/outline "Switch to the Cloud of your choice" button, X close). Closed with the X.

### SQL Editor
- Left side is a second sidebar overlaying the main one: "Queries" heading, an icon-only close X at its right, tabs "All / Favorites", search field "Search queries" with a magnifier, a "New query" button (white, grey), and list items: "List users", "Postgres 17.3 Release Notes", "Chat with Supabase AI" (small "AI" label), "Reset your organization password", "List users" (duplicate), "Disable Realtime for table", "Create ENUM type", "Disable RLS". During load, skeleton bars and spinners fill the pane; the list is long and vertically scrollable.
- Main pane: a tab "New" (with a small "…" menu), below a dark toolbar reading "supabase" and "Run query", then a large empty white editor area with faint placeholder text "Type your SQL query here" at top-left.
- Toolbar above the editor (left to right): "Save" (pale grey button with disk icon, disabled), "Prettify" (white, small icon), **Run** — solid dark-green pill button with a white play triangle at its left and a separate chevron segment at its right (split-button), "Database" (white button with a small star/grid icon and chevron), and an icon-only "…" button.
- Header/button row above that: "New tab" (white button with + icon), "Results" (white button with a small icon), and a green "Ask AI Assistant" outline button (white fill, green text, lightning/bolt icon) at top-right. A toast appeared top-right: "Snippet no longer exists". No query was typed; Run was not pressed.

### Database → Tables
- Header: heading "Tables", right side a "Search tables" field with a magnifier, a "Schema: public" dropdown (white), a white "Refresh"/reset icon button (circular arrows), a white "View" dropdown, and a solid dark-green pill **New table** with a white + at its left.
- Table: white, light-grey borders, columns "NAME | COLUMNS | ROWS | SIZE | HYPERDRIVE | REALTIME | DESC" (small grey uppercase header row); one row per table with a small grey table icon before a dark bold name, size in plain text "48 kB", and the Realtime column showing a small grey × icon in a circle with the word "Disabled" in grey. No per-row action buttons in the main list.
- Contents: 3 tables — "email_login_codes" (8 columns, 7 rows, 48 kB), "profiles" (4 columns, 2 rows, 32 kB), "sessions" (4 columns, 6 rows, 48 kB). "Hyperdrive" and "Desc" are empty for all rows. A thin horizontal scrollbar ("Schema Visualizer — Tables 3/3 shown") appears below the table; before loading, skeletons (grey boxes) were shown in the table area.
- Note: clicking "Database" in the main sidebar first lands on "Schema Visualizer" (/database/schemas) — a dotted canvas with white schema cards (profiles, sessions, email_login_codes) and a bottom toolbar of icons plus a white "Show tables" pill and an orange/pink "Publish" button, and a chevron link "Expand [4] schemas". The Tables page is reached from the Database sub-sidebar ("DATABASE MANAGEMENT": Schema Visualizer, Tables, Backups, Migrations, Roles, Replications, Functions, Extensions, MR API, plus "CONFIGURATION": Policies, Triggers, Webhooks, Settings).

### Database → Functions
- Header: heading "Functions", intro text "Update your Postgres database functions in the SQL editor", right side a "Search functions" field with magnifier, a "Schema: public" dropdown (white), a white "View" dropdown, and a solid dark-green pill **New Function** with a white + at its left.
- Table: white, columns "NAME | ARGUMENTS | RETURN TYPE | SECURITY | SCHEMA", rows alternating white/pale with a small light-grey "f" icon at left of the name, a small light-blue/grey TypeScript-style icon at the left of the function name, and a small grey copy icon button at the far right end of each row. "SECURITY" column reads "Definer" for all rows.
- Contents: 12 functions, all with (…)=blank argument — "send_auth_sms" (text), "create_system_session" (text), "invoke_send_sms_driver" (text), "record_outbox_event" (text), "process_outbox_event" (uuid), "generate_signup_token" (text), "retry_failed_outbox_events" (integer), "generate_magic_link" (text), "get_user_id_by_email" (uuid), "cleanup_expired_login_codes" (integer), "mark_outbox_event_as_failed" (boolean), "generate_login_code" (text). All under schema public.
- Below the table, a reminder line: "Learn more about Postgres functions" as a link, and a note that some functions are system functions.

### Database → Extensions
- Header: heading "Extensions", right side a "Search extensions" field with magnifier, a checkbox "Show official extensions only" (with a "Learn more" link), a white "Refresh" button (circular arrows), a white "Show all" dropdown, a white "Sort by name" dropdown, and a solid dark-green pill **New extension** with a white + at its left.
- Table: white, columns "NAME | VERSION | SCHEMA | DESCRIPTION | USED BY | LINKS | ENABLED". Each row has a green square icon at left of the "NAME" link (dark text), version "1.0" or "1.4" in grey, schema "public"/"extensions", a small grey "Description" area, "Used by" showing a small grey external-link icon and count ("1", "5" or "—"), "LINKS" showing a small external-link icon, and "ENABLED" showing a toggle switch — on is solid dark-green with a white knob at right, off is solid light-grey with knob at left. No other buttons per row.
- Contents: "64 extensions" total. The first four are enabled (green toggles ON): pgcrypto 1.3, uuid-ossp 1.1 (with a small grey "DEPRECATED" tag), plpgsql 1.0, pg_stat_statements 1.11. The rest are OFF (grey toggles): pg_graphql, pg_net, pgsodium, pg_trgm, plpgsql_check, protocol, plv8, plv8_check, postgis, postgres_fdw, pg_tle, lt_param, plan, postgis-3, "pg_stat_kcache" and others. A notice at top of the results says enabling some extensions may require a restart.

### Authentication → Users
- Header: heading "Users", right side a "Search users" field with magnifier, a white "Filter" button with chevron, a white "Properties" button with chevron and small icon, a white "Add" icon button, and a solid dark-green pill **Add user** (white + icon at left) with a small chevron at its right (split).
- Auth sub-sidebar: "CONFIGURATION" — Users (active), Authentication, Policies, Templates, Rate Limits, Emails, Providers, Settings, plus a "USER MANAGEMENT" group.
- Table: white with thin grey gridlines, headers: (checkbox) FIRST NAME LAST NAME | EMAIL | USER ID | PHONE | PROVIDERS | CONFIRMED EMAIL | CREATED AT | LAST SIGN IN | (more). Rows show an avatar circle with an initial, the email address as the first column, plus the user ID UUID string and created date/time "Nov 6, 2026, 11:48 AM" / "Nov 6, 2026, 11:55 AM" and "Last sign in" timestamps. Table is horizontally scrollable — on a 1920 px window the rightmost "Last sign in" column is cut off and a horizontal scrollbar appears at the bottom.
- Contents: 2 users, both email (hamza…@gmail.com and ahmad…@gmail.com), UID beginning 24d9c1… and 67db82… respectively. One other row is visible at the very bottom of the pane as a third entry (no data). No empty state.

### Storage → Buckets
- Storage sidebar: "FILES" heading with a small "files" folder icon, "STORAGE" sub-sidebar with "Files", "Buckets" (active), "Policies" and a "STORAGE METRICS" group.
- Header for Buckets: heading "Buckets", below "Storage" as small heading; tabs "Files" and "Buckets" with a small "1 Files/Buckets" count line. Right side: a "Search buckets" field (magnifier), a white "Sorted by" dropdown, a white "Refresh" button with circular-arrows icon, and a solid dark-green pill **New bucket** with a white + icon.
- Bucket list: a single full-width white row with a small horizontal-line icon at left, the bucket name dark bold text "user-files", a large "0" at right edge (count), "Policies" label below/left, "Unset (50 MB)" in grey, "Any" label, and a small grey ">" chevron at right end of the row, indicating the row opens details. There was 1 bucket total.
- The Files view (default landing) shows an empty dashed area: "No files in this bucket", a link "Create a new folder", and a breadcrumb-style header with the bucket name; it also has a "Create folder" button reading "+ New folder". No drag-and-drop area or other buckets.

### Edge Functions
- Header: heading "Edge Functions", below a white bar with a "Search" field, a "Search functions" field, and a white "Load more" button (plus an option button).
- Empty state: NO functions deployed. The page shows grey skeleton bars while loading, then an empty-state panel: "Deploy your first function" heading (left-aligned), text "Edge Functions executes code in Deno that runs at the edge of the world", plus two buttons side by side: "Open Editor" (white with a small lightning/bolt icon) found under "Via Editor", and "Open Assistant" (white) under "AI Assistant"; "View CLI Instructions" (white) under "Via CLI". A small note: "Prepare your first Edge Function with the AI Assistant".
- Below, a list of template cards, each a full-width white bordered row with a small icon at left, a bold name and a one-line description with a button at right: "Hello World — Deno middleware for handling user authentication", "Confirm Signup — Confirm user signup with SendGrid or Mailgun", "Use with Resend", "Easy Chat with GPT", "Update content securely", "Use Stripe Webhooks", "Use Supabase Vault…" and others (12 templates named in the page, including "Stripe" and "Integrate with Slack").
- No green primary button on this page except the heading-level action buttons; the main actions are all white secondary buttons.

### Realtime (Inspector)
- Header: heading "Realtime" (small heading level 4), left sub-sidebar: "TOOLS" — Inspector (active, grey), Policies, Settings; plus "CONFIGURATION" — Policies, Settings.
- Top toolbar (white secondary buttons): "Join a channel" (white, grey channel icon with chevron), "Role" (white, with "postgres" in a light-grey pill), "Start listening" — pale mint-green button with a play icon (DISABLED, grey/green text), and "Filter messages" (white, grey filter icon) at right.
- Main empty panel: centred illustration — a small animated graphic of two paper-plane icons (green and orange) — heading "Create realtime experiences", text "Use the Inspector to build Realtime experiences", and a solid dark button "Set up realtime for me" (dark/charcoal, white text).
- Below, three numbered steps in a list, each with a numbered circle, a bold heading and a small description with a blue "Documentation" link: "1 Broadcast messages — Create a trigger", "2 Write policies — Write a policy for your table", "3 Subscribe to a channel — Subscribe to a channel". Bottom of the panel also shows a note line about "Create a trigger" with a chevron arrow at right.
- No rows, no messages, no data — an empty/inspector state.

### Logs (Unified Logs)
- Header: heading "Unified Logs" with a "BETA" pill (small, light background) and a "NEW" pill; below a blue info banner "Introducing unified logs — View all your logs in one place" with a "More information" link and a "Dismiss banner" X button at right.
- Toolbar (white buttons with grey icons): "Hide filters" (white), "Search logs" field with magnifier, "Time range" (white, "Last 1 hour" with chevron), "Hide filters", "Scroll to top", "Download logs", "View logs", and a dark-green "Run" button (solid, white text) after the date range controls.
- Left filter panel (narrow, white, about 260 px wide): headings "Filters", "Timestamp", "Level", "Product", "Message", with checkboxes and counts: API Gateway 84, Postgres 13, PostgREST 0, Auth 14, Storage 33, Edge 0, Realtime 1, Supavisor 0, PgBouncer 68, Compute 0; Level: Success 86, Warning 11, Error 0. A small "x" clear icon appears next to each active filter category.
- Above the table, a histogram/timeline chart (bars, light-grey/green) with a time scale.
- Table: white, headers "DATE | METHOD | PATHNAME | PIPELINE ID | EVENT | MESSAGE". Rows are mostly log entries for API/REST and are dense; many cells in the visible area are blank (a grey "—" placeholder), with entries showing a date/time, a "GET" or similar method label (grey pill), a path such as "/rest/v1/profiles" and a "Pipeline ID" value. "50 of 97 rows" and a scrolling list with a bottom bar showing the counted results. No colour-coded severity in the visible rows (success/warning are counted in the filters instead).

### Project Settings → General
- Header: heading "General", subheading text about project settings. Left sub-sidebar groups: "PROJECT" — General (active), Database, API, Authentication, Storage, Edge Functions, Realtime, Logs, Integration; plus "ORGANIZATION" — General, Members, Billing, Usage, Domains.
- Cards (white, rounded, light-grey border, stacked vertically, each with a small grey icon at left of its title):
  - "Project name" — label, text field prefilled "data cleaning studio's Project", no save button visible in the card.
  - "Project reference ID" — read-only field showing "tembowfascqjqgtqumlw" and a "Copy ref" button (white, grey link icon).
  - "Service versions" — rows: "Auth" version "2.197.0" with a pale-green outline pill "LATEST"; "PostgREST" 14.18 "LATEST"; "Postgres" "17.11.0.018" with a pale-green "LATEST" pill. Each row has a small grey "?" icon and a small "Copy" link at right.
  - "Custom domains" — text about adding a custom domain, with a dark-green solid button "Upgrade to Pro" at right (no icon).
  - "Transfer project" — truck icon, text "Transfer this project to another organization", white secondary button "Transfer project" at right (no icon).
  - "Delete project" — warning card with a pale red/pink background, red trash-can icon, title "Delete project" and explanatory text; a solid dark-red button "Delete project" at bottom-left (white text). This button was NOT clicked.
- Secondary setting details visible elsewhere in the page: "Remove project" note, "Project restoration" note, and a small note that the project's backups can be restored from the "Backups" page.
- Note: the Settings page does not use a green primary CTA except "Upgrade to Pro" (dark green); most actions are white secondary buttons.

### Account menu (top-right avatar)
- Clicking the circular avatar (black circle, white person icon) at top-right opens a white dropdown panel (rounded corners, soft shadow, about 280 px wide) anchored just below the avatar, on top of the page.
- Header inside the menu: the user's email "ahmadfed966@gmail.com" in bold dark text at top, with a small grey sub-line.
- Items, each a row with a grey icon at left and dark text, stacked (no separators between some): "Account" (person icon), "Feature previews" (flask/beaker icon), "Changelog" (document icon).
- Below that: "Theme" section heading in small grey, with three rows — "System" (with a filled dark radio dot at right = selected), "Dark" (dark moon icon), "Light" (sun icon); then "Timezone" heading with a row "Auto (Asia/Calcutta)" and a ">" chevron at right.
- Footer: a full-width solid dark-green button "Upgrade to Pro" (white text, no icon), then a plain text item "Sign out" (dark text, no icon, no border).
- The menu was closed with Escape; Sign out was not clicked.
- **Rebuild note:** Supabase's real menu has NO "Profile" button (it has "Account") and NO standalone theme-switch button — the theme is a three-row radio section (System / Dark / Light). Our avatar menu should be rebuilt to match this, not the soul pass's version.

### Button pattern — summary for the rebuild (confirmed live)
- Primary green action: solid dark-green background, white label, white icon at left of the label when an icon exists (+ for new/create, play triangle for Run; Connect has a plug/link icon that is dark-on-green). Shape is usually **pill (fully rounded)** for "New table" / "New bucket" / "New Function" / "Add user", **rectangular with rounded corners** for "Connect", "Insert row" and "Run" (Run has a split chevron segment). **No Supabase logo mark appears on any button.**
- Secondary: white background, light-grey border, dark text, small grey icon at left; the top navigation "Connect" is the only green button in the global top bar.
- Danger: solid red ("Delete project"). Disabled: pale grey/mint with muted text.
- Logo: no large Supabase wordmark in the dashboard header or on buttons; the project/org avatar and selector sit top-left, and the small Supabase mark is at the top of the left navigation.

### What is still unstudied after both tracks
- Compute, Advisors, Observability, Integrations, org home, Auth sub-pages beyond Users, Database sub-pages beyond Tables/Functions/Extensions/Schema Visualizer (Backups, Migrations, Roles, Replications, Policies, Triggers, Webhooks), Settings sub-pages beyond General. (Table Editor grid and Auth Users were also covered by the earlier design study, not only this walk.)
