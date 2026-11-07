# Data Cleaner Studio — web version

> **STATUS (2026-11-06): Phase 1 is built and verified working in local
> mode, and Phase 2 is now integrated.** The Streamlit app (`app.py`)
> is complete: the full v1.4 feature set from the desktop `.exe`, with
> local (SQLite) accounts and per-user server storage — and the
> Supabase wiring is done in the app itself (connection status in
> Settings, real Google sign-in button, OAuth callback handling).
> **No Supabase project exists yet, no accounts have been created
> and nothing has been deployed** — without `supabase_config.json`
> the app runs in local mode, which is still the default. The cloud
> userbase goes live when the user creates the free project and
> adds the config (steps below). Hosting is the user's decision and
> needs his word + payment details (see [DEPLOY.md](DEPLOY.md)).

The web version of Data Cleaner Studio: the same tested Python engine
as the desktop `.exe` (load messy CSV / Excel / JSON / Google Sheets,
profile, clean, KPIs, export a cleaned workbook), running as a
Streamlit app on a server, with user accounts and per-user server
storage.

## Phase 1 vs Phase 2

- **Phase 1 (done):** the full app, verified working in
  **local mode** — SQLite accounts on the server, per-user folders
  under `data/users/`, all v1.4 features (live DB connections,
  chunked big-file cleaning, Parquet, daily auto-clean setup,
  white-label brand, tutorial, live Excel formulas, live currency
  rates, mobile layout).
- **Phase 2 (integrated 2026-11-06, no live project yet):** the
  Supabase userbase is wired into `app.py` — Settings shows the
  connection status (backend, config file present or not, any
  warning verbatim), the login screen shows a real "Continue with
  Google" button when Supabase is configured (and a plain "needs
  Supabase" note in local mode), and the `?code=` OAuth callback
  is exchanged for a session. `auth.py` (Supabase Auth + Postgres,
  via `supabase-py`) and `storage.py` (Supabase Storage) were
  already ready; the app now presents them. It goes live when the
  user creates the free project: create it (his own Supabase
  account), run `supabase_setup.sql`, add `supabase_config.json`,
  restart the app. See [DEPLOY.md](DEPLOY.md) section 0 for the
  steps. Until then local mode is the default, and everything
  still works exactly as in Phase 1.

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/streamlit run app.py
```

Then open http://localhost:8501. (Python 3.12.)

Without Supabase configured, the app runs in **LOCAL MODE** (SQLite
accounts in `data/users.db`, per-user folders under `data/users/`,
with a banner saying so). Local mode is fully usable — the cloud
backend is only needed for hosted multi-user auth. See "Auth" below
and [DEPLOY.md](DEPLOY.md) for the Phase 2 setup steps.

The refresh scheduler runs as a separate process — it is not part of
the Streamlit app:

```bash
# Single pass (for cron / a systemd timer):
.venv/bin/python scheduler.py --once

# Or a long-running loop:
.venv/bin/python scheduler.py --daemon
```

## Project structure

```
app.py                    Streamlit app — full v1.4 port of the .exe UI
engine.py                 Cleaning engine (copied verbatim from the .exe project)
feat_*.py                 Feature modules (analyse, combine, db, export, ...)
ai_settings.py            AI settings helpers
auth.py                   User accounts — Supabase primary, SQLite local fallback
storage.py                Per-user server storage under data/users/<username>/
                          (cloud mode routes through Supabase Storage)
google_auth.py            Google sign-in (Supabase Auth OAuth; Phase 2)
scheduler.py              Server-side refresh daemon (Google Sheets / DB -> user folders)
supabase_config.json.example
supabase_setup.sql        Postgres tables for Phase 2 (users, sessions, ...)
data/
  users.db                LOCAL MODE accounts DB (SQLite; never commit)
  users/<username>/       Per-user files: uploads/, cleaned/, recipes/,
                          views/, workspaces/
  scheduler/
    jobs.json             Refresh job registry (created by the app; see scheduler.py)
    jobs.json.example     Example registry — disabled jobs, no real data
    scheduler.log         Scheduler run log
requirements.txt          Runtime deps (streamlit, pandas, altair, openpyxl,
                          pypdf, supabase)
Dockerfile                python:3.12-slim image, Streamlit on :8501
.dockerignore             Keeps data/ and Supabase secrets OUT of the image
DEPLOY.md                 Hosting options, Supabase setup, costs
tests/
  test_web_smoke.py       AppTest smoke test: signup -> login -> upload ->
                          clean -> dashboard; wrong password fails;
                          user isolation; share link + revoke
  test_*.py               Engine/feature tests copied from the .exe project
  smoke_test.py           The .exe project's smoke test (superseded here
                          by test_web_smoke.py)
```

## Auth: Supabase (Phase 2, integrated) + local mode (default)

**Local mode (what runs today, no config needed):** user accounts
live in **SQLite** (`data/users.db`, PBKDF2-hashed passwords, 7-day
sessions), per-user folders, and a banner in the UI saying local
mode is active. Sign up with a username + password (3–30
characters, letters/digits/underscore; password 8+ characters).
Google sign-in is not available in local mode — the login screen
says so plainly ("Google sign-in needs Supabase configured").

**Supabase (wired in, goes live with a config file):** user
accounts and user records live in **Supabase Auth + Postgres** via
`supabase-py`. The app needs one file in the project folder (or the
equivalent environment variables / Streamlit secrets on Community
Cloud — see [DEPLOY.md](DEPLOY.md)):

- `supabase_config.json` — Project URL + anon key (copy
  `supabase_config.json.example` and fill it in)

Then run `supabase_setup.sql` in the Supabase SQL editor to create
the tables. Until that file exists, the app runs in local mode.
Local accounts and Supabase accounts are different users —
switching backends means re-registering.

> **NEVER commit `supabase_config.json`.** It is listed in
> `.gitignore` and `.dockerignore`. The service-role key must never
> be in a file at all — it lives only in the
> `SUPABASE_SERVICE_ROLE_KEY` environment variable (server-side).
> If a key ever leaks, roll it in the Supabase dashboard.

**Email login code (Brevo, free 300/day):** every password login —
and every sign-up — asks for a 6-digit code sent to the user's
email. The code is the login check and the email verification in
one, and it replaces the old Cloudflare Turnstile check (removed).
Set it up in Brevo first (free account, verify a sender address,
generate a v3 API key), then add the key and sender to the app's
Streamlit secrets as `BREVO_API_KEY` and `BREVO_SENDER_EMAIL`.
With no key configured the app refuses password logins with a clear
setup message — the code check is never bypassed. Google sign-in
is exempt (Google already verified the email); local mode has no
email addresses, so the check does not apply there. Codes expire
after 10 minutes, allow 5 wrong tries, and a new one can be
requested no sooner than 60 seconds after the last (5 per hour).

### If the Supabase project ever pauses (free tier)

Free-tier Supabase projects **pause after 1 week with no real
database activity** — and only real queries count: just opening
the app's page does **not** reset the clock. Restoring a paused
project is **one click in the Supabase dashboard, and no data is
lost**. The app does not crash when this happens: it shows
**"Project paused — restore it in the Supabase dashboard"**
(via `auth.get_backend_warning()`, displayed on the login screen
and in Settings) instead of faking a login or failing silently.

Keeping the project awake is a side effect of the scheduled
refresh jobs: the scheduler daemon's refresh queries are real
database activity, so a job every 3 days (the default when you
create one in Settings) keeps the project inside the 3–4 day
keep-alive window. The scheduler daemon itself handles the actual
keep-alive queries (`supabase_keepalive()`); the app only sets
the default and explains it.

## How refreshes work (scheduler)

`scheduler.py` reads `data/scheduler/jobs.json` and refreshes due jobs:
Google Sheets via `engine.load_sheets_url`, databases via `feat_db`
against a saved connection (`data/users/<user>/connections/<name>.json`).
It writes results atomically, never lets one user's job touch another
user's files, and logs every run to `data/scheduler/scheduler.log`.
It works off the per-user folders + job registry and is **independent of
the auth backend** — local or Supabase mode makes no difference to it.
On Streamlit Community Cloud the daemon cannot run (no background
processes — see [DEPLOY.md](DEPLOY.md)); scheduled refresh needs a VPS.

## Sharing

The Dashboard tab can create a **read-only share link**
(`?share=<token>`). It shows a saved snapshot of the KPIs and chart
numbers — not live data, not the user's files — and anyone with the
link can open it without logging in. Links are listed in
Settings, where they can be revoked; a revoked link shows
"revoked or does not exist".

## Tests

```bash
python3 -m venv .test-venv
.test-venv/bin/pip install -r requirements.txt -r requirements-test.txt pytest
.test-venv/bin/python tests/test_web_smoke.py        # the web smoke test
.test-venv/bin/python -m pytest tests/ --ignore=tests/smoke_test.py -q
```

Results (2026-11-06, local mode, fresh `.test-venv` with
`streamlit==1.66.1 pandas==3.1.1 altair openpyxl pypdf
supabase==2.34.0`): web smoke test passes (login gate, clean,
share/revoke, isolation, logout, checkboxes control cleaning);
`test_auth_storage.py` passes; `test_auth_supabase.py` passes
(structural only — no live Supabase project exists, nothing
contacted a live backend: missing config → local + banner,
malformed config → local + warning, unreachable project →
"Project paused" message + clean `AuthServiceError`, never a fake
login); a Phase 2 AppTest check passes (login screen shows the
"needs Supabase" Google note, Settings shows the Supabase status
section, unreachable URL gives the paused message verbatim); live
`streamlit run app.py` headless: health endpoint 200, app page
200, no errors. Full pytest in that run: **206 passed**, 5 failed in
`tests/test_feat_db.py`. Update (2026-11-06): `requirements.txt`
now ships the DB drivers (`mysql-connector-python==26.10.0`,
`psycopg2-binary==2.9.13`, `pymssql==2.4.6`), so the 3 driver tests
pass in the main venv — `tests/test_feat_db.py` is now 7 passed /
2 failed, the 2 failures being the Windows PyInstaller wheel-file
checks, which do not apply to the web repo
(`hidden_files/wheels/` does not exist here). `tests/smoke_test.py`
targets the `.exe` app and is superseded by
`test_web_smoke.py`.

## Honest limits

- **Your data leaves your computer.** Files live on the server, not on
  your machine. Whoever hosts the server (you, or a provider) can see
  the files. If that matters, self-host on a VPS you control.
- **Hosting costs money** (except the Streamlit Community Cloud free
  tier, which has limits — see [DEPLOY.md](DEPLOY.md)). First deploy
  needs the user's decision + payment details.
- **AI features need your own API key** in Settings (Groq and/or
  Gemini, stored per user in your folder). No key is ever baked
  into the app, the image, or the repo.
- **Database refresh needs the right driver installed** on the server
  (MySQL / PostgreSQL / SQL Server). A DB job whose driver is missing
  is marked failed with a clear reason — it never fails silently.
- **Streamlit Community Cloud free tier**: 1 GB RAM, the app sleeps
  after inactivity, and the scheduler daemon cannot run there.
- **Local mode is single-server**: accounts live in a SQLite file on
  that server. Moving servers means moving `data/` (or switching on
  Supabase in Phase 2, which is the point of it being primary).
- **Per-user file redirection is per-process, not per-session** (see
  the note at the top of `app.py`): the hard isolation (auth
  sessions, storage folders, share snapshots) does not depend on it,
  but two users hitting the server in the same instant share the
  module-level settings/views paths. Fine at this scale; revisit
  before a busy multi-user launch.
