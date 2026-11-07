# Deploying Data Cleaner Studio (web)

> **STATUS (2026-11-06): NO accounts created, NOTHING deployed.** There is
> no Supabase project, no cloud account, no VPS, no domain. Everything
> below is a plan with real numbers. **Hosting is the user's decision** —
> it needs his word, and any paid option needs his payment details.
> The app itself (`app.py`) is built and Phase 1-verified in local mode,
> and the Supabase wiring is integrated (Phase 2). Nothing has talked to
> a live Supabase project yet — the first deploy still needs his
> Supabase project + hosting decision.

## 0. Supabase setup (the user does this himself) — FREE tier only

Supabase is the primary user database + auth (Supabase Auth +
Postgres + Storage). The user creates the project under **his own
account** at https://supabase.com — nobody else should own it.
Everything below is free; nothing here asks for a card.

1. Go to https://supabase.com → **Sign up / Sign in** → **New project**
   → name it (e.g. `data-cleaner-studio`) → pick a region close to the
   users (e.g. `Mumbai (ap-south-1)`) → create it. Wait a minute or two
   while it provisions.
2. **Copy the URL and anon key:** **Settings (gear) → API** → copy the
   **Project URL** (`https://<your-ref>.supabase.co`) and the **anon
   public key**. Paste them into **`supabase_config.json`** in the
   project folder (copy `supabase_config.json.example` and fill it in).
   **Never commit it** — it is in `.gitignore` and `.dockerignore`.
3. **Create the tables:** **SQL Editor → New query** → paste the whole
   of **`supabase_setup.sql`** (in the project folder) → **Run**. This
   creates the `profiles` + `sessions` tables, the five helper
   functions the app calls, and the private `user-files` Storage bucket
   with per-user policies. Safe to run again; it is idempotent.
4. **Email sign-in is on by default** (no step needed). One choice:
   **Authentication → Providers → Email → "Confirm email"**. Supabase
   turns confirmation ON by default, which means a new user must click
   a link in their inbox before they can log in. For this app, turn
   **Confirm email OFF** so signup logs straight in (simpler; the app
   already requires 8+ character passwords). If you leave it on, the
   app tells the user plainly to check their inbox.
5. **Google sign-in (optional):** **Authentication → Providers →
   Google → Enable** → paste the Google OAuth Client ID + Secret (from
   Google Cloud Console → Credentials → OAuth client, free). Then
   **Authentication → URL Configuration → Redirect URLs** → add the
   app's URL (e.g. `https://<app>.streamlit.app` or your domain).
   Without this step, Google sign-in shows "not set up yet" and
   email/password still works.
6. **Storage (only if Supabase-mode file storage is wanted):** the
   server needs the **service-role key** as the
   `SUPABASE_SERVICE_ROLE_KEY` environment variable (VPS: systemd
   `Environment=` or a `.env` the service reads; Streamlit Cloud:
   Secrets). **Never put it in a file, never commit it, never show it
   in the browser.** It is the only key that bypasses Row Level
   Security, and the server needs it because the app's sessions are
   custom tokens, not Supabase JWTs (see storage.py). If it is not
   set, Supabase-mode file operations fail loudly with a clear
   message instead of silently writing locally. Auth (signup/login)
   works fine without it — only file storage needs it.

```jsonc
// supabase_config.json — example shape (values are placeholders, not real)
{
  "url": "https://YOUR-PROJECT-REF.supabase.co",
  "anon_key": "PASTE_YOUR_ANON_KEY_HERE"
}
```

**Until `supabase_config.json` exists, the app runs in LOCAL MODE**
(SQLite accounts in `data/users.db`, per-user folders, banner shown in
the UI). Deployment is **not blocked on Supabase** — local mode works
end to end for testing and single-user use, and the scheduler does not
care which auth backend is active for local-mode users (it works off
the per-user folders + job registry).

On Streamlit Community Cloud there is no project folder to drop files
into, so the same two values go through the **Cloud secrets manager**
instead (TOML secrets — see option A). The app reads them from
`SUPABASE_URL` / `SUPABASE_ANON_KEY` environment variables as a
fallback when no config file exists.

### Free-tier limits (what "free" actually means)

| Limit | Free tier |
| --- | --- |
| Database size | 500 MB |
| Monthly active users | 50,000 |
| File storage | 1 GB |
| Data egress | 5 GB / month |
| Projects | 2 |
| **Cost** | **$0** |

At this app's scale (a handful of users, small CSVs) none of these
limits is close. Only if usage grows past them would anything charge
— and that needs the user's word first.

### The auto-pause (read this — it surprises everyone)

A free Supabase project **pauses after 1 week of inactivity** — and
"inactivity" means **no real database activity**: actual queries
(login, load, save, SELECT/INSERT). Just opening the app's page does
NOT count. Two things handle this:

- **Keep-alive (automatic):** the scheduler runs one tiny real query
  (a SELECT on the profiles table) at most once every 3 days, tracked
  in `data/scheduler/keepalive.json`. Those queries double as the
  keep-alive, so the project stays awake even if nobody opens the app
  for a week — as long as the scheduler is running (VPS daemon or a
  cron running `scheduler.py --once` every day or two). On Streamlit
  Cloud there is no scheduler, so a Cloud-only deploy relies on real
  user logins to keep the project awake.
- **If it does pause anyway:** the app does not crash — it shows the
  plain message **"Project paused — restore it in the Supabase
  dashboard"**. Restoring is **one click** in the Supabase dashboard
  (the paused project shows a **Restore** button) and **no data is
  lost** — everything (users, files, tables) comes back exactly as it
  was. The only way to remove the pause behaviour entirely is the Pro
  plan ($25/month) — and the user has chosen to stay free, so the
  keep-alive + one-click restore is the plan.

---

## Option A — Streamlit Community Cloud (free tier)

The cheapest way to get a public link. Good for a demo / first users.
Not suitable for scheduled refresh (see limits).

### Steps

1. Push this folder to a **public GitHub repo** (free tier requires a
   public repo unless invited to a private app).
2. Go to https://share.streamlit.io → **New app** → pick the repo,
   branch, and `app.py` as the main file → **Deploy**.
3. **Secrets:** App settings → **Secrets** — paste the Supabase values
   as TOML:

```toml
SUPABASE_URL = "https://YOUR-PROJECT-REF.supabase.co"
SUPABASE_ANON_KEY = "paste-the-anon-key-here"
# Only if Supabase-mode file storage is wanted (server-side only):
SUPABASE_SERVICE_ROLE_KEY = "paste-the-service-role-key-here"
# Email login code (Brevo, free 300/day) — required for password
# logins: the app sends a 6-digit code to the user's email on every
# login and sign-up. Get them from the Brevo dashboard (free account,
# verify a sender address, then SMTP & API → API Keys). Without these
# lines the app refuses password logins with a setup message — the
# code check is never bypassed.
BREVO_API_KEY = "paste-the-brevo-api-key-here"
BREVO_SENDER_EMAIL = "your-verified-sender@example.com"
```

   Never put secrets in the repo. Without them the app runs in local mode.
4. Share the `https://<app>.streamlit.app` link.

### Limits (honest)

- **1 GB RAM.** Large files / big clean jobs can hit the ceiling.
- **The app sleeps after inactivity** and takes ~30–60 s to wake on the
  next visit.
- **No background processes.** `scheduler.py --daemon` **cannot run**
  here — there is no always-on process and no SSH. Scheduled refresh
  does not happen on Cloud; data refreshes only when a user opens the
  app (on-demand refresh) or after moving to a VPS. The Supabase
  keep-alive also does not run here, so a Cloud-only deploy relies on
  real user logins to keep the free project awake (see "The
  auto-pause" above — restore is one click, no data lost).
- **Public repo required** on the free tier (private apps need an
  invite / paid plan). The code is public; user data is not in the
  repo — but remember the repo is visible to everyone, so secrets in
  git would be a real leak.
- No custom domain on the free URL (a custom domain is possible via
  Cloud settings on paid plans; otherwise the `streamlit.app` URL is
  what users get).

---

## Option B — VPS (recommended for real use)

A small VPS runs everything: the Streamlit app, the scheduler daemon,
and HTTPS. This is the only option where scheduled refresh (and the
Supabase keep-alive) works.

**Example servers** (prices checked against the providers' list prices;
they change — confirm at signup):

- **Hetzner CX22 — ~€4–5/month** (~€4.15 + VAT; 2 vCPU, 4 GB RAM,
  40 GB SSD). Cheapest serious option.
- **DigitalOcean Basic droplet — ~$6/month** (1 vCPU, 1 GB RAM,
  25 GB SSD). The 2 GB / $12 tier is roomier if files get big.

### Steps

1. Create the server with **Ubuntu 24.04**, note its IP. Point a domain
   at it if you have one (A record → server IP); a domain is optional
   at first, the IP works for testing.
2. SSH in and install the base stack:

```bash
sudo apt update && sudo apt install -y python3.12 python3.12-venv nginx certbot python3-certbot-nginx git
```

3. Clone the repo and set up the app (as a non-root user, e.g. `dcs`):

```bash
git clone <repo-url> /opt/data-cleaner-studio
cd /opt/data-cleaner-studio
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

4. Supabase config (if using Supabase auth): place
   `supabase_config.json` in `/opt/data-cleaner-studio/` (owned by
   the `dcs` user, mode `600`). Without it the app runs in local mode.
   If Supabase-mode file storage is wanted, also set the service-role
   key as an environment variable for both services below
   (`Environment=SUPABASE_SERVICE_ROLE_KEY=...` in the systemd units)
   — never in a file, never in git.
5. **systemd service — the Streamlit app** (`/etc/systemd/system/dcs-app.service`):

```ini
[Unit]
Description=Data Cleaner Studio web app
After=network.target

[Service]
Type=simple
User=dcs
WorkingDirectory=/opt/data-cleaner-studio
ExecStart=/opt/data-cleaner-studio/.venv/bin/streamlit run app.py --server.port 8501 --server.address 127.0.0.1
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

6. **systemd service — the scheduler daemon** (`/etc/systemd/system/dcs-scheduler.service`):

```ini
[Unit]
Description=Data Cleaner Studio refresh scheduler
After=network.target

[Service]
Type=simple
User=dcs
WorkingDirectory=/opt/data-cleaner-studio
ExecStart=/opt/data-cleaner-studio/.venv/bin/python scheduler.py --daemon
Restart=on-failure
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

   (Alternative: run `scheduler.py --once` from a systemd timer / cron
   every 15 minutes instead of the daemon. The daemon is simpler and
   already respects each job's own interval. Either way, the scheduler
   is what runs the Supabase keep-alive query every 3 days, so keep
   it running even when no refresh jobs are configured.)

7. Enable and start both, then check the logs:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dcs-app dcs-scheduler
sudo systemctl status dcs-app dcs-scheduler
sudo journalctl -u dcs-scheduler -f   # or tail data/scheduler/scheduler.log
```

8. **nginx reverse proxy** (`/etc/nginx/sites-available/dcs`):

```nginx
server {
    listen 80;
    server_name your-domain.com;   # or the server IP for testing

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/dcs /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

9. **HTTPS with Let's Encrypt** (needs a domain — skip this step if
   testing on the raw IP):

```bash
sudo certbot --nginx -d your-domain.com
```

10. Verify: open `https://your-domain.com`, create a test account,
    upload a file, and check `data/scheduler/scheduler.log` shows the
    daemon ticking (and a `KEEP-ALIVE | ok` line within 3 days).

### Docker alternative (same VPS)

If Docker is preferred over venv + systemd:

```bash
docker build -t data-cleaner-studio .
docker run -d --name dcs --restart unless-stopped \
  -p 127.0.0.1:8501:8501 \
  -v dcs-data:/app/data \
  -v /opt/data-cleaner-studio/supabase_config.json:/app/supabase_config.json:ro \
  -e SUPABASE_SERVICE_ROLE_KEY="$SUPABASE_SERVICE_ROLE_KEY" \
  data-cleaner-studio
# plus a second container for the scheduler:
docker run -d --name dcs-scheduler --restart unless-stopped \
  -v dcs-data:/app/data \
  -v /opt/data-cleaner-studio/supabase_config.json:/app/supabase_config.json:ro \
  -e SUPABASE_SERVICE_ROLE_KEY="$SUPABASE_SERVICE_ROLE_KEY" \
  data-cleaner-studio python scheduler.py --daemon
```

The Dockerfile has not been build-tested yet (no Docker on this
machine) — treat the first real `docker build` as the test. Secrets are
mounted read-only at run time (config file) or passed as environment
variables (service-role key), never baked into the image.

---

## Monthly-cost table

| Item | A: Streamlit Cloud (free) | B: VPS — Hetzner CX22 | B: VPS — DigitalOcean |
| --- | --- | --- | --- |
| Hosting | $0 | ~€4–5 / month | ~$6 / month |
| Domain (optional) | $0 (uses `*.streamlit.app`) | ~$10–15 / year (~$1 / month) | ~$10–15 / year (~$1 / month) |
| Supabase (free tier) | $0 | $0 | $0 |
| SSL (Let's Encrypt) | included | $0 | $0 |
| **Total, first year** | **$0** | **~€60–75 / year** | **~$84–90 / year** |
| Scheduled refresh | **No** (daemon can't run) | Yes | Yes |
| Supabase keep-alive | No (relies on logins) | Yes (scheduler) | Yes (scheduler) |
| Sleeps when idle | Yes | No | No |

Domain registrars for the ~$10–15/year figure: Namecheap, Cloudflare
Registrar, Porkbun — a `.com` is typically $10–15/year; prices vary by
TLD and registrar.

## What is NOT done

- No Supabase project exists. No accounts, no billing.
- No VPS, droplet, domain, or SSL certificate has been bought.
- No repo has been pushed, no Cloud app deployed.
- The Dockerfile has never been built (no Docker on this machine).
- The systemd units and nginx config above are written but **untested**
  — they get proven on the first real deploy.
- Google sign-in and Supabase Storage have never been live-tested
  (no project exists yet); both are structural-only until the project
  is created and the flows are tried once.

Picking an option, creating accounts, and spending money are the user's
call. When he says go, the order is: (1) Supabase project (his account,
free tier — URL + anon key, run `supabase_setup.sql`), (2) GitHub repo,
(3) Cloud free tier first to prove the app, (4) VPS only if scheduled
refresh or the Cloud limits start to bite.
