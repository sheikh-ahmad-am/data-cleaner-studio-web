-- Data Cleaner Studio (web) — Supabase setup. FREE TIER ONLY.
--
-- Run this ONCE in the Supabase dashboard: SQL Editor -> New query ->
-- paste this whole file -> Run. It is safe to run again (idempotent):
-- tables, functions, bucket and policies are all created "if not
-- exists" or dropped-and-recreated.
--
-- What it creates:
--   * public.profiles  — one row per user (id = Supabase Auth user id)
--   * public.sessions  — the app's server-side 7-day session tokens
--   * 5 SECURITY DEFINER functions the app calls via client.rpc().
--     RLS is ON with NO permissive policies on either table, so the
--     anon key cannot read or write them directly — only these
--     functions can, and each does exactly one narrow job.
--   * A private Storage bucket `user-files` + per-user policies.
--
-- STORAGE NOTE (read before changing paths): the policies below say a
-- user may only touch objects whose FIRST path segment equals their
-- Supabase Auth user id — that governs DIRECT client access. The app
-- server itself reaches the bucket with the service-role key (never
-- in the repo, env var only) and enforces per-user isolation in
-- Python after its own session check (see storage.py). The server's
-- object paths use the app's storage key, not the auth uid.
--
-- COST: everything here is inside the free tier (500 MB database,
-- 50,000 monthly active users, 1 GB file storage, 5 GB egress/month).
-- No paid feature is used. A free project pauses after 1 week of
-- inactivity; the scheduler runs a tiny keep-alive query every 3
-- days so that does not happen on its own, and restoring a paused
-- project is one click in the dashboard — no data is lost.

-- ------------------------------------------------------------------
-- Tables
-- ------------------------------------------------------------------

create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.sessions (
  token text primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null
);

create index if not exists idx_sessions_user_id
  on public.sessions (user_id);

-- RLS on, no permissive policies: direct access with the anon key is
-- denied. Only the SECURITY DEFINER functions below may touch these
-- tables on the app's behalf.
alter table public.profiles enable row level security;
alter table public.sessions enable row level security;

-- ------------------------------------------------------------------
-- Functions (called by auth.py via client.rpc)
-- ------------------------------------------------------------------

-- Create or update the profile row for a user; returns the row as JSON.
create or replace function public.app_upsert_profile(p_id uuid, p_email text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  result jsonb;
begin
  insert into public.profiles (id, email)
  values (p_id, p_email)
  on conflict (id) do update set email = excluded.email
  returning to_jsonb(profiles) into result;
  return result;
end;
$$;

-- Read one profile row; returns the row as JSON, or null.
create or replace function public.app_get_profile(p_id uuid)
returns jsonb
language sql
security definer
set search_path = public
as $$
  select to_jsonb(p) from public.profiles p where p.id = p_id;
$$;

-- Store one app session token (7-day expiry, set by the caller).
create or replace function public.app_create_session(
  p_token text, p_user_id uuid, p_created_at timestamptz, p_expires_at timestamptz
)
returns void
language sql
security definer
set search_path = public
as $$
  insert into public.sessions (token, user_id, created_at, expires_at)
  values (p_token, p_user_id, p_created_at, p_expires_at)
  on conflict (token) do update set
    user_id = excluded.user_id,
    created_at = excluded.created_at,
    expires_at = excluded.expires_at;
$$;

-- Validate a token: drops expired sessions, returns the user id, or null.
create or replace function public.app_validate_session(p_token text)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user_id uuid;
begin
  delete from public.sessions where expires_at <= now();
  select user_id into v_user_id
  from public.sessions where token = p_token;
  return v_user_id;
end;
$$;

-- Delete one session token (logout). No error when it does not exist.
create or replace function public.app_delete_session(p_token text)
returns void
language sql
security definer
set search_path = public
as $$
  delete from public.sessions where token = p_token;
$$;

-- Only the anon + authenticated roles may call these (revoke the
-- default PUBLIC grant first so the surface is explicit).
revoke execute on function public.app_upsert_profile(uuid, text) from public;
revoke execute on function public.app_get_profile(uuid) from public;
revoke execute on function public.app_create_session(text, uuid, timestamptz, timestamptz) from public;
revoke execute on function public.app_validate_session(text) from public;
revoke execute on function public.app_delete_session(text) from public;
grant execute on function public.app_upsert_profile(uuid, text) to anon, authenticated;
grant execute on function public.app_get_profile(uuid) to anon, authenticated;
grant execute on function public.app_create_session(text, uuid, timestamptz, timestamptz) to anon, authenticated;
grant execute on function public.app_validate_session(text) to anon, authenticated;
grant execute on function public.app_delete_session(text) to anon, authenticated;

-- ------------------------------------------------------------------
-- Storage: private bucket + per-user policies (direct client access)
-- ------------------------------------------------------------------

insert into storage.buckets (id, name, public)
values ('user-files', 'user-files', false)
on conflict (id) do nothing;

-- A user may only read/write objects whose first path segment is
-- their own Supabase Auth user id. The app server uses the
-- service-role key instead and enforces the same boundary in Python.
drop policy if exists "users read own files" on storage.objects;
create policy "users read own files"
  on storage.objects for select to authenticated
  using (
    bucket_id = 'user-files'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists "users write own files" on storage.objects;
create policy "users write own files"
  on storage.objects for insert to authenticated
  with check (
    bucket_id = 'user-files'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists "users update own files" on storage.objects;
create policy "users update own files"
  on storage.objects for update to authenticated
  using (
    bucket_id = 'user-files'
    and (storage.foldername(name))[1] = auth.uid()::text
  )
  with check (
    bucket_id = 'user-files'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists "users delete own files" on storage.objects;
create policy "users delete own files"
  on storage.objects for delete to authenticated
  using (
    bucket_id = 'user-files'
    and (storage.foldername(name))[1] = auth.uid()::text
  );
