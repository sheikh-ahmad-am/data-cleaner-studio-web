# Changelog — Data Cleaner Studio

What changed, newest first. Every row traces back to the git history
by its short commit hash. The same entries live in the app, in the
Status tab ("What's new") — see `feat_status.py`.

| Date | Milestone | What changed for you |
| --- | --- | --- |
| 2026-11-07 | Email login code replaces the security check (`c4c862f`) | Nothing — logging in and signing up now ask for a 6-digit code sent to your email instead of the old security check. The code expires in 10 minutes; if it does not arrive, use Resend. |
| 2026-11-06 | Rebuilt on the Supabase design system (`6ce9c8a`) | Nothing — the whole app was restyled (near-white, one green, hairline borders) and works exactly as before. |
| 2026-11-06 | Profile section added (`fa9aa3f`) | Nothing — open Profile from the sidebar to see your account, change your display name, reset your password, download your data, or delete your account. |
| 2026-11-06 | Cleaner look: light theme, guided empty states (`845b1fd`) | Nothing — the app is lighter and the empty screens now say what to do next instead of leaving a blank page. |
| 2026-11-06 | Security check on login and sign-up (`da01db8`) | Nothing — a Cloudflare security check now runs when you log in or sign up. If it ever blocks you, reload and try again. |
| 2026-11-06 | Fix batch: login survives refresh, 26 fixes (`1d1311e`) | Nothing — logging in now survives a page refresh, and 26 issues found by end-to-end testing were fixed. |
| 2026-11-06 | First version (`24b3b0a`) | Nothing — the first working version: upload a file, clean it, see KPIs and a report. |
