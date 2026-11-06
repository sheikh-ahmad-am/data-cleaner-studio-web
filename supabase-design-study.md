# Supabase Dashboard — Design Study (2026-11-06)

Source: live dashboard for project "data cleaning studio's Project"
(tembowfascqjqgtqumlw), studied read-only via browser on 2026-11-06
23:02–23:05 IST. Pages: project home, Authentication > Users,
Table Editor (profiles grid). Hex values sampled from rendered pixels.
Typeface described from observation (Inter, Supabase's standard UI font).

## Shared tokens

- Page/app background: `#fdfdfd` (near-white, very slightly warm).
  Top bar, content area, and secondary sidebar all share it — no
  separate grey app canvas.
- Card/panel background: `#ffffff` (pure white).
- Border/hairline: `#e8e8e8` (light warm grey) — card edges, table
  gridlines, dotted diagram grid. Button borders ~`#e4e4e4`;
  checkbox borders ~`#d0d0d0`.
- Corner radius: cards 10–12px; buttons ~6px; icon boxes ~8px;
  pills/badges fully rounded; inputs ~6px.
- Primary button: background `#117f50` (deep forest green, sampled
  range #0f7e4e–#118051), white text, ~6px radius, ~26–28px tall,
  compact padding. Split button in places (chevron segment right).
- Brand greens: logo mark `#3ecf8e` (classic bright green); node/icon
  green `#16b674`; pale mint pill fill `#e9f8f1`. Green is used
  sparingly — the dashboard is mostly monochrome; green is reserved
  for brand + primary actions + success (logo, primary buttons,
  spinner, status dots, "Healthy" icon, diagram icons).
- Amber/orange accent (BETA / PRODUCTION pills): pale cream fill
  `#f4ece3`, amber border/text `#f3ba63` / `#e69344`, uppercase,
  ~10px, letterspaced, fully rounded. Warning dots amber; error
  dots red.
- Typography: clean neutral grotesque sans (Inter). H1 (project name)
  ~28px, medium weight, near-black `#030303`. Section headings
  ("Get connected", "Users") ~16–18px medium. Sidebar section labels
  and card micro-labels: uppercase, ~10–11px, wide letterspacing,
  mid-grey `#696969`. Body ~13–14px, near-black. Secondary/muted
  text mid-grey.
- Sidebar, two layers: far-left icon rail ~46px wide, `#fdfdfd`,
  thin 1px outline icons (Lucide-style line icons, ~18px, dark
  grey/black). Secondary sidebar ~260px wide, `#fdfdfd`, separated
  by a hairline. Nav items are plain text rows (~30px tall, ~13px)
  grouped under tiny uppercase section labels (MANAGE /
  NOTIFICATIONS / CONFIGURATION). Active item = `#f3f3f3` rounded
  pill background, semibold black text, dark left-edge indicator.
  Hover = very subtle `#f8f8f8` wash; hover also shows a dark
  tooltip (with keyboard-shortcut hints).
- Top bar (~48px, `#fdfdfd`, hairline bottom border): breadcrumb
  "Org FREE / Project / main PRODUCTION" (names are links with
  chevron pickers), green Connect button at right, then "Feedback",
  a "Search... Ctrl K" pill input, round monochrome icon buttons
  (Help, Advisor Center, SQL Editor, AI Assistant, avatar).
- Motion/loading: green circular spinner on load, then grey skeleton
  bars that fade into content; hover states subtle and instant (no
  long transitions); tooltips on hover; thin grey horizontal
  scrollbar when content overflows.

## Page 1 — Project home / overview

Large H1 project name (near-black), project URL in grey below with a
small white "Copy" split-button. Left column: six status tiles in two
columns, each a white ~48px square icon box (thin `#eaeaea` border,
~8px radius) beside an uppercase micro-label (STATUS, COMPUTE SIZE,
GITHUB, RECENT BRANCH, LAST MIGRATION, LAST BACKUP) and a value
("Healthy", "NANO" chip, "No repository connected"...). Right: large
white canvas card with a faint dotted grid (`#e8e8e8` dots) holding
one floating "Primary Database" node card — green DB icon `#16b674`,
"South Asia (Mumbai) · ap-south-1 · Nano", India flag, metric strip
"CPU 2% · Disk 15% · RAM 53% · 8/60 conns". Below: "Get connected"
section — six equal white cards in one row (Framework / Server /
Direct / ORM / MCP / API Keys), each with a small line icon, bold
title, grey subtitle, separated by hairlines. Then a stats strip
"157 Total Requests · 56.1% Success Rate" with a white "Last 60
minutes" dropdown, and horizontally scrollable metric cards
(API GATEWAY 92, STORAGE 36, AUTH 17, POSTGRES 9, REALTIME 3, EDGE
FUNCTIONS 0) — each white, ~10px radius, uppercase label, large
count, WARNINGS (amber dot) / ERRORS (red dot) counts. Overall:
airy, flat (almost no drop shadow — borders do the work), calm,
data-dense but with generous whitespace.

## Page 2 — Authentication > Users

Sidebar header "Authentication" with MANAGE/NOTIFICATIONS/
CONFIGURATION groups and BETA pills (Passkeys, OAuth Server, Auth
Hooks). Content header "Users" (H3, ~18px, semibold). Filter bar:
white rounded inputs — "Email address" dropdown, "Search by email"
textbox, "All columns", disabled "Sorted by user ID" pill, refresh
icon button, green "Add user" split button. Table: white background,
header row of small semibold dark text (UID, Display name, Email,
Phone, Providers, Provider type, Created at, Last sign in at) with a
bottom hairline; rows separated by `#e8e8e8` hairlines, ~40px tall,
compact; row checkboxes small rounded squares (~16px, `#d0d0d0`
border). "Providers" cell is a small rounded pill — pale warm/cream
background (sampled ~`#fde5a7` near its icon) with a mail icon and
"Email" text. Timestamps plain dark grey text. Footer: "Total: 10
users (estimated)". Table wider than viewport, grey horizontal
scrollbar. Feel: dense, spreadsheet-like admin table, minimal chrome.

## Page 3 — Table Editor (profiles grid)

Header: "Table Editor" label + "schema public" dropdown + white "New
table" button. Table-list sidebar (search box, "profiles" active with
dark left bar, "sessions"). Grid area: light-grey (`#efefef`) tab
strip with a white active tab "profiles" (+ a "+" tab). Toolbar:
plain filter input "Filter by id, email, created_at or ask AI",
Sort, "Add RLS policy" (white pill, green plus), "Role postgres"
dropdown, refresh, green "Insert" split button. Grid: white
background; header row with column names in bold (id, email,
created_at) + grey type labels (uuid, text, timestamptz) and small
dropdown carets; narrow row-select checkbox column; cells plain dark
text on white with `#e8e8e8` vertical/horizontal gridlines;
primary-key cell has a key/link icon; a dashed "+" column invites
adding columns. Footer bar: pagination (Page 1 of 1, "100 rows",
"2 records") and Definition/Data toggle. White feature banner
bottom-right ("NEW" mint pill `#e9f8f1`, mini diff preview with red
"- Red" and green "+ Blue" lines, "Queue row edits in Table
Editor"). Feel: the most compact/dense of the three — a true
spreadsheet grid: white, hairline-ruled, monochrome except for the
green Insert button.

## Marketing site — visual tokens (2026-11-06 23:13–23:15 IST)

Source: live public pages supabase.com, supabase.com/pricing,
supabase.com/docs, studied read-only via browser. Hex values
pixel-sampled at 1919px viewport; sizes estimated from measured
glyph heights; sans family reported as Inter-like on appearance
(computed font-family not exposed by the browser tooling).

- Page background: `#FDFDFD` (near-white). Cards `#FFFFFF`;
  subtle panel/inline-code grey `#F8F8F8`–`#FAFAFA`.
- Headings: near-black `#030303`. Body `#4D4D4D`–`#484848`;
  muted supporting text `#696969`. Nav links black `#030303`,
  ~14px, medium weight.
- Two greens, used differently: brand/logo green `#3ECF8E`
  (sampled from the logo mark); UI green for buttons, hero
  highlight, icons, in-text links is much darker, `#0F7E4E` /
  `#107F4F`. Primary button is NOT flat: subtle vertical gradient
  `#118050` (top) → `#0E7D4E` (bottom), white text, ~148×36px,
  ~8px corner radius (rounded rectangle, NOT a pill), medium-weight
  label. Secondary/ghost button: white `#FFFFFF`, 1px light-grey
  hairline border (~`#E5E5E5`), black text, same height/radius.
- Gradients: essentially none in UI chrome or hero — hero, nav,
  cards, code panels are flat. Gradients appear only as
  editorial/brand colour in customer-story cards.
- Cards/panels: flat, no visible drop shadow — 1px hairline borders
  `#EAEAEA`–`#EFEFEF`, radius ~8px (pricing plan cards ~12px).
- Typography: clean neo-grotesque sans (Inter-like), tight tracking
  on headings. Monospace for plan prices, tier labels, code.
  Code ~13–14px; inline code on a `#F8F8F8` pill; code panels are
  WHITE with a hairline border and coloured syntax (purple
  keywords, orange/green strings) — notably NOT a dark code block.
- Nav: sticky, 64px tall on marketing/pricing, hairline bottom
  border, solid `#FDFDFD` at top; on scroll translucent with
  backdrop blur. Docs nav slimmer (~50px), "supabase DOCS" with a
  Search pill (Ctrl K) and "Ask AI" button.
- Layout: centred containers, generous whitespace — homepage ~1100px
  wide, pricing ~1370px, Docs ~1260px. Section spacing ~120–160px.
  Footer is LIGHT (not dark): "We protect your data" security strip
  (SOC2, HIPAA, ISO 27001), newsletter input, small ~12–13px link
  columns.
- Motion: no hero video or autoplay animation; hero is static.
  Interactive motion is functional: dashboard tabs swap the product
  screenshot, framework tabs swap the code example, community section
  is a masonry of tweets with faded edges (slow scrolling columns),
  hover states subtle. Theme toggle exists in the footer
  (light/dark); session rendered light mode.

### Homepage — "Build in a weekend / Scale to millions"

- Hero H1 ~48px, weight ~500 (medium, not bold), line-height
  ~1.05–1.1; line 1 black `#030303`, line 2 dark green `#0E7E4E`.
  Subtext ~16–18px, muted `#696969`. Buttons "Start your project"
  (primary green) and "Request a demo" (white/ghost).
- Section headings ~28–32px, weight 500–600, black; several are
  two-tone (grey first line + black second line). Product cards
  (Postgres Database, Authentication, Edge Functions, Storage,
  Realtime, Vector, Data APIs) are white, hairline-bordered, small
  green line icons, ~16px bold titles, grey body.
- Feel: airy, minimal, developer-tool clean — white space, hairline
  rules, restrained colour (green is the only accent), product
  imagery doing the visual work.

### Pricing — "Predictable pricing, designed to scale"

- Same system. H1 ~36–40px black, grey subtext. Four plan cards:
  FREE $0, PRO $25/mo, TEAM $599/mo, ENTERPRISE Custom. Tier names
  uppercase monospace (~13px); prices large monospace (~32–36px)
  black. Pro is the highlighted card ("Most Popular" dark pill,
  slightly stronger border).
- Interactive: Pro/Team segmented toggle, compute calculator ("Drag
  to adjust" slider, dark knob, live estimate), "Spend Cap" toggle
  (on, green), accordions ("Expand Pricing breakdown", FAQ). Feature
  comparison table: hairline row dividers, green checkmarks; in-text
  links black/underlined rather than green.
- Feel: the most product-dense page — same light system, but tabular,
  mono numerals, calculator-driven; green used sparingly.

### Docs — "Supabase Documentation"

- Same light background (`#FCFCFC`–`#FDFDFD`) and near-black headings;
  utilitarian layout, no big hero art. H1 ~32px; H2s ("Connect a
  framework", "Build your backend", "Extend your database") ~20px,
  weight 500–600; body ~15–16px, `#4D4D4D`.
- Card index, not prose: framework tiles (icon in ~8px rounded
  square + name), larger white cards with green line icons
  (Database, Auth, Storage, Realtime, Edge Functions). "Agent
  Prompt" / CLI tab panel under the H1 with "Copy Agent Prompt"
  button and numbered setup steps with inline mono commands.
  Inline code chips `#F8F8F8`. Footer: minimal "Need some help? /
  Contact support / See Changelog / Check system status" strip.
- Feel: the quietest page — clean, flat index, scannable cards and
  search ("Search Ctrl K" + "Ask AI" in the top bar).

## How to use this in the reskin

- Replace the Classic palette with these tokens: bg `#fdfdfd`,
  cards `#ffffff`, borders `#e8e8e8`, primary `#117f50`, brand
  green `#3ecf8e` (logo/accents), ink `#030303`, muted `#696969`.
- Radii: cards 10–12px, buttons/inputs 6px, pills fully rounded.
- Type: Inter (sans-serif fallback), H1 28px medium, sections
  16–18px, micro-labels uppercase 10–11px letterspaced.
- Flat: borders, not shadows. Green sparingly (primary actions +
  success only). Amber pills for beta/warning states.
- Motion: green spinner + skeleton fade on load; subtle instant
  hovers; tooltips. Streamlit cannot do full SPA motion — hover
  transitions and fades only.
