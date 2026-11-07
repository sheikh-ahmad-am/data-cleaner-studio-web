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
--   * public.email_login_codes — salted hashes of the 6-digit login
--     codes (never the plain code), with expiry, attempts and a used
--     flag; one row per code request
--   * 11 SECURITY DEFINER functions the app calls via client.rpc().
--     RLS is ON with NO permissive policies on any table, so the
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

-- One row per login-code request: only the salted SHA-256 hash is
-- stored (never the plain code), plus expiry, wrong-try count and a
-- used flag. RLS on, no policies — only the functions below touch it.
create table if not exists public.email_login_codes (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  code_hash text not null,
  salt text not null,
  expires_at timestamptz not null,
  attempts integer not null default 0,
  used boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists idx_login_codes_email
  on public.email_login_codes (email);

-- Profile: the name shown in the app (null until the user sets one).
alter table public.profiles
  add column if not exists display_name text;

-- RLS on, no permissive policies: direct access with the anon key is
-- denied. Only the SECURITY DEFINER functions below may touch these
-- tables on the app's behalf.
alter table public.profiles enable row level security;
alter table public.sessions enable row level security;
alter table public.email_login_codes enable row level security;

-- pgcrypto supplies digest() for the code-hash comparison inside
-- app_verify_login_code (the plain code is hashed there with the
-- stored salt and never stored).
create extension if not exists pgcrypto;

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

-- Set a user's display name; returns the updated row as JSON
-- (null when the profile row does not exist).
create or replace function public.app_set_display_name(p_id uuid, p_display_name text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  result jsonb;
begin
  update public.profiles p set display_name = p_display_name where p.id = p_id
  returning to_jsonb(p) into result;
  return result;
end;
$$;

-- List a user's sessions as metadata only (never the token values).
create or replace function public.app_list_sessions(p_user_id uuid)
returns table(created_at timestamptz, expires_at timestamptz)
language sql
security definer
set search_path = public
as $$
  select created_at, expires_at from public.sessions
  where user_id = p_user_id order by created_at desc;
$$;

-- Delete a user's sessions + profile row, in one transaction.
-- (The Supabase Auth user itself is deleted through the auth admin
-- channel, not here.)
create or replace function public.app_delete_account_data(p_user_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  delete from public.sessions where user_id = p_user_id;
  delete from public.profiles where id = p_user_id;
end;
$$;

-- Request a login code: enforces the 60-second resend cooldown and
-- the 5-codes-per-hour cap, invalidates any older active code for
-- the email, then stores the salted hash. Returns 'ok', 'too_soon'
-- or 'hourly_limit'. The plain code is never stored — the caller
-- (auth.py) hashes it first.
create or replace function public.app_request_login_code(
  p_email text, p_code_hash text, p_salt text, p_expires_at timestamptz
)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  v_last timestamptz;
  v_count integer;
begin
  -- Cooldown: only an ACTIVE code imposes one. A used row (consumed
  -- by a successful login, or invalidated after a failed Brevo send)
  -- must not block the next request — a failed send retries at once.
  p_email := lower(trim(p_email));
  select created_at into v_last
  from public.email_login_codes
  where email = p_email and used = false order by created_at desc limit 1;
  if v_last is not null and now() - v_last < interval '60 seconds' then
    return 'too_soon';
  end if;
  select count(*) into v_count
  from public.email_login_codes
  where email = p_email and created_at >= now() - interval '1 hour';
  if v_count >= 5 then
    return 'hourly_limit';
  end if;
  update public.email_login_codes set used = true
  where email = p_email and used = false;
  insert into public.email_login_codes (email, code_hash, salt, expires_at)
  values (p_email, p_code_hash, p_salt, p_expires_at);
  return 'ok';
end;
$$;

-- Verify a login code: returns 'ok', 'wrong', 'expired', 'too_many'
-- or 'not_found'. Wrong tries are counted; 5 wrong tries (or an
-- expiry) invalidates the code. The plain code is hashed inside the
-- function with the stored salt and compared to the stored hash —
-- it is never stored.
create or replace function public.app_verify_login_code(p_email text, p_code text)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  v_row public.email_login_codes%rowtype;
begin
  p_email := lower(trim(p_email));
  p_code := replace(trim(p_code), ' ', '');
  select * into v_row
  from public.email_login_codes
  where email = p_email and used = false
  order by created_at desc limit 1;
  if v_row.id is null then
    return 'not_found';
  end if;
  if v_row.expires_at <= now() then
    update public.email_login_codes set used = true where id = v_row.id;
    return 'expired';
  end if;
  if v_row.attempts >= 5 then
    update public.email_login_codes set used = true where id = v_row.id;
    return 'too_many';
  end if;
  if v_row.code_hash = encode(digest(v_row.salt || p_code, 'sha256'), 'hex') then
    update public.email_login_codes set used = true where id = v_row.id;
    return 'ok';
  end if;
  if v_row.attempts + 1 >= 5 then
    update public.email_login_codes set used = true, attempts = v_row.attempts + 1 where id = v_row.id;
    return 'too_many';
  end if;
  update public.email_login_codes set attempts = v_row.attempts + 1 where id = v_row.id;
  return 'wrong';
end;
$$;

-- Invalidate any active code for an email (a send that failed, or a
-- fresh request). No error when none exists.
create or replace function public.app_invalidate_login_code(p_email text)
returns void
language sql
security definer
set search_path = public
as $$
  update public.email_login_codes set used = true
  where email = lower(trim(p_email)) and used = false;
$$;

-- Only the anon + authenticated roles may call these (revoke the
-- default PUBLIC grant first so the surface is explicit).
revoke execute on function public.app_upsert_profile(uuid, text) from public;
revoke execute on function public.app_get_profile(uuid) from public;
revoke execute on function public.app_create_session(text, uuid, timestamptz, timestamptz) from public;
revoke execute on function public.app_validate_session(text) from public;
revoke execute on function public.app_delete_session(text) from public;
revoke execute on function public.app_set_display_name(uuid, text) from public;
revoke execute on function public.app_list_sessions(uuid) from public;
revoke execute on function public.app_delete_account_data(uuid) from public;
revoke execute on function public.app_request_login_code(text, text, text, timestamptz) from public;
revoke execute on function public.app_verify_login_code(text, text) from public;
revoke execute on function public.app_invalidate_login_code(text) from public;
grant execute on function public.app_upsert_profile(uuid, text) to anon, authenticated;
grant execute on function public.app_get_profile(uuid) to anon, authenticated;
grant execute on function public.app_create_session(text, uuid, timestamptz, timestamptz) to anon, authenticated;
grant execute on function public.app_validate_session(text) to anon, authenticated;
grant execute on function public.app_delete_session(text) to anon, authenticated;
grant execute on function public.app_set_display_name(uuid, text) to anon, authenticated;
grant execute on function public.app_list_sessions(uuid) to anon, authenticated;
grant execute on function public.app_delete_account_data(uuid) to anon, authenticated;
grant execute on function public.app_request_login_code(text, text, text, timestamptz) to anon, authenticated;
grant execute on function public.app_verify_login_code(text, text) to anon, authenticated;
grant execute on function public.app_invalidate_login_code(text) to anon, authenticated;

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
