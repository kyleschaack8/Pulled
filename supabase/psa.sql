-- =====================================================================
-- Pulled: PSA cert verification (run after setup.sql)
-- Paste into Supabase -> SQL Editor -> New query -> Run. Safe to run again.
-- =====================================================================

-- Saved PSA lookups. Only the psa-cert function writes here (it uses the
-- service role); everyone can read them, so a cert is looked up once and
-- reused, which keeps Pulled well under PSA's daily limit.
create table if not exists public.psa_certs (
  cert text primary key check (cert ~ '^[0-9]{6,10}$'),
  found boolean not null,
  data jsonb check (data is null or pg_column_size(data) <= 4000),
  fetched_at timestamptz not null default now(),
  checked_by uuid references public.profiles (id) on delete set null
);
create index if not exists psa_certs_fetched on public.psa_certs (fetched_at desc);
alter table public.psa_certs enable row level security;

drop policy if exists "psa lookups are public" on public.psa_certs;
create policy "psa lookups are public" on public.psa_certs for select to anon, authenticated using (true);

revoke all on public.psa_certs from anon, authenticated;
grant select (cert, found, data, fetched_at) on public.psa_certs to anon, authenticated;
grant all on public.psa_certs to service_role;

-- a post can carry the slab's cert number
alter table public.posts add column if not exists psa_cert text;
alter table public.posts drop constraint if exists posts_psa_cert_check;
alter table public.posts add constraint posts_psa_cert_check check (psa_cert is null or psa_cert ~ '^[0-9]{6,10}$');
