-- =====================================================================
-- Pulled: database setup for Supabase
-- Paste this whole file into Supabase -> SQL Editor -> New query -> Run.
-- Safe to run more than once.
--
-- Creates: profiles, posts, comments, likes, follows, messages,
-- collection items (cards owned + wishlist), card submissions,
-- and a public "photos" storage bucket. Every table has row level
-- security: anyone can read public things (posts, profiles, collections),
-- people can only change their own, and messages are private to the
-- two people in the conversation.
-- =====================================================================

-- ---------- profiles (one per account) ----------
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  handle text not null check (handle ~ '^[A-Za-z0-9_]{3,20}$'),
  bio text not null default '' check (char_length(bio) <= 160),
  fav text not null default 'All' check (fav in ('All', 'NBA', 'NFL', 'MLB', 'NHL', 'Soccer')),
  hue int not null default 200 check (hue between 0 and 359),
  is_admin boolean not null default false,
  created_at timestamptz not null default now()
);
create unique index if not exists profiles_handle_lower on public.profiles (lower(handle));

-- make a profile automatically when someone signs up
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
  base text := left(coalesce(nullif(regexp_replace(coalesce(new.raw_user_meta_data ->> 'handle', ''), '[^A-Za-z0-9_]', '', 'g'), ''), 'collector'), 15);
  h text;
  f text := coalesce(new.raw_user_meta_data ->> 'fav', 'All');
begin
  if char_length(base) < 3 then base := base || 'fan'; end if;
  h := base;
  while exists (select 1 from public.profiles where lower(handle) = lower(h)) loop
    h := base || floor(random() * 9000 + 1000)::int;
  end loop;
  if f not in ('All', 'NBA', 'NFL', 'MLB', 'NHL', 'Soccer') then f := 'All'; end if;
  insert into public.profiles (id, handle, fav, hue) values (new.id, h, f, floor(random() * 360)::int);
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- is the signed-in person a moderator?
create or replace function public.is_admin()
returns boolean language sql stable security definer set search_path = '' as $$
  select coalesce((select is_admin from public.profiles where id = auth.uid()), false)
$$;

-- ---------- posts ----------
create table if not exists public.posts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  card text not null check (char_length(card) between 1 and 80),
  kind text not null check (kind in ('pulled', 'bought', 'graded', 'sale', 'trade')),
  caption text not null default '' check (char_length(caption) <= 280),
  ask int check (ask is null or ask between 1 and 10000000),
  photo_url text check (photo_url is null or (char_length(photo_url) <= 400 and photo_url like 'https://%/storage/v1/object/public/photos/%')),
  created_at timestamptz not null default now()
);
create index if not exists posts_created on public.posts (created_at desc);
create index if not exists posts_user on public.posts (user_id);

-- ---------- comments ----------
create table if not exists public.comments (
  id uuid primary key default gen_random_uuid(),
  post_id uuid not null references public.posts (id) on delete cascade,
  user_id uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  body text not null check (char_length(body) between 1 and 280),
  created_at timestamptz not null default now()
);
create index if not exists comments_post on public.comments (post_id);

-- ---------- likes ----------
create table if not exists public.likes (
  post_id uuid not null references public.posts (id) on delete cascade,
  user_id uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (post_id, user_id)
);

-- ---------- follows ----------
create table if not exists public.follows (
  follower uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  followee uuid not null references public.profiles (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (follower, followee),
  check (follower <> followee)
);

-- ---------- private messages ----------
create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  sender uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  recipient uuid not null references public.profiles (id) on delete cascade,
  body text not null check (char_length(body) between 1 and 1000),
  created_at timestamptz not null default now(),
  read_at timestamptz,
  check (sender <> recipient)
);
create index if not exists messages_sender on public.messages (sender, created_at);
create index if not exists messages_recipient on public.messages (recipient, created_at);

-- ---------- collections: cards people own ('have') and want ('want') ----------
create table if not exists public.items (
  user_id uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  card text not null check (char_length(card) between 1 and 80),
  list text not null check (list in ('have', 'want')),
  status text not null default 'keep' check (status in ('keep', 'trade', 'sale')),
  ask int check (ask is null or ask between 1 and 10000000),
  created_at timestamptz not null default now(),
  primary key (user_id, card, list)
);

-- ---------- card submissions from the scanner ----------
create table if not exists public.submissions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  key text not null check (char_length(key) <= 300),
  fields jsonb not null default '{}'::jsonb check (pg_column_size(fields) <= 4000),
  front_url text check (front_url is null or (char_length(front_url) <= 400 and front_url like 'https://%/storage/v1/object/public/photos/%')),
  back_url text check (back_url is null or (char_length(back_url) <= 400 and back_url like 'https://%/storage/v1/object/public/photos/%')),
  status text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  created_at timestamptz not null default now(),
  unique (user_id, key)
);
create index if not exists submissions_key on public.submissions (key);

-- ---------- row level security ----------
alter table public.profiles enable row level security;
alter table public.posts enable row level security;
alter table public.comments enable row level security;
alter table public.likes enable row level security;
alter table public.follows enable row level security;
alter table public.messages enable row level security;
alter table public.items enable row level security;
alter table public.submissions enable row level security;

drop policy if exists "profiles are public" on public.profiles;
create policy "profiles are public" on public.profiles for select to anon, authenticated using (true);
drop policy if exists "make own profile" on public.profiles;
create policy "make own profile" on public.profiles for insert to authenticated with check (id = (select auth.uid()));
drop policy if exists "edit own profile" on public.profiles;
create policy "edit own profile" on public.profiles for update to authenticated using (id = (select auth.uid())) with check (id = (select auth.uid()));

drop policy if exists "posts are public" on public.posts;
create policy "posts are public" on public.posts for select to anon, authenticated using (true);
drop policy if exists "post as yourself" on public.posts;
create policy "post as yourself" on public.posts for insert to authenticated with check (user_id = (select auth.uid()));
drop policy if exists "edit own posts" on public.posts;
create policy "edit own posts" on public.posts for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
drop policy if exists "delete own posts" on public.posts;
create policy "delete own posts" on public.posts for delete to authenticated using (user_id = (select auth.uid()) or (select public.is_admin()));

drop policy if exists "comments are public" on public.comments;
create policy "comments are public" on public.comments for select to anon, authenticated using (true);
drop policy if exists "comment as yourself" on public.comments;
create policy "comment as yourself" on public.comments for insert to authenticated with check (user_id = (select auth.uid()));
drop policy if exists "delete own comments" on public.comments;
create policy "delete own comments" on public.comments for delete to authenticated using (
  user_id = (select auth.uid())
  or exists (select 1 from public.posts p where p.id = post_id and p.user_id = (select auth.uid()))
  or (select public.is_admin()));

drop policy if exists "likes are public" on public.likes;
create policy "likes are public" on public.likes for select to anon, authenticated using (true);
drop policy if exists "like as yourself" on public.likes;
create policy "like as yourself" on public.likes for insert to authenticated with check (user_id = (select auth.uid()));
drop policy if exists "unlike own" on public.likes;
create policy "unlike own" on public.likes for delete to authenticated using (user_id = (select auth.uid()));

drop policy if exists "follows are public" on public.follows;
create policy "follows are public" on public.follows for select to anon, authenticated using (true);
drop policy if exists "follow as yourself" on public.follows;
create policy "follow as yourself" on public.follows for insert to authenticated with check (follower = (select auth.uid()));
drop policy if exists "unfollow own" on public.follows;
create policy "unfollow own" on public.follows for delete to authenticated using (follower = (select auth.uid()));

drop policy if exists "read own conversations" on public.messages;
create policy "read own conversations" on public.messages for select to authenticated using ((select auth.uid()) in (sender, recipient));
drop policy if exists "send as yourself" on public.messages;
create policy "send as yourself" on public.messages for insert to authenticated with check (sender = (select auth.uid()));
drop policy if exists "mark own messages read" on public.messages;
create policy "mark own messages read" on public.messages for update to authenticated using (recipient = (select auth.uid())) with check (recipient = (select auth.uid()));

drop policy if exists "collections are public" on public.items;
create policy "collections are public" on public.items for select to anon, authenticated using (true);
drop policy if exists "add to own collection" on public.items;
create policy "add to own collection" on public.items for insert to authenticated with check (user_id = (select auth.uid()));
drop policy if exists "edit own collection" on public.items;
create policy "edit own collection" on public.items for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
drop policy if exists "remove from own collection" on public.items;
create policy "remove from own collection" on public.items for delete to authenticated using (user_id = (select auth.uid()));

drop policy if exists "submissions are public" on public.submissions;
create policy "submissions are public" on public.submissions for select to anon, authenticated using (true);
drop policy if exists "submit as yourself" on public.submissions;
create policy "submit as yourself" on public.submissions for insert to authenticated with check (user_id = (select auth.uid()) and status = 'pending');
drop policy if exists "moderators review" on public.submissions;
create policy "moderators review" on public.submissions for update to authenticated using ((select public.is_admin())) with check ((select public.is_admin()));
drop policy if exists "withdraw own or moderate" on public.submissions;
create policy "withdraw own or moderate" on public.submissions for delete to authenticated using ((user_id = (select auth.uid()) and status = 'pending') or (select public.is_admin()));

-- ---------- what the website is allowed to touch ----------
-- (needed because "Automatically expose new tables" is off)
grant usage on schema public to anon, authenticated;
revoke all on public.profiles, public.posts, public.comments, public.likes, public.follows, public.messages, public.items, public.submissions from anon, authenticated;

grant select (id, handle, bio, fav, hue, created_at) on public.profiles to anon, authenticated;
grant insert (id, handle, bio, fav, hue), update (handle, bio, fav, hue) on public.profiles to authenticated;

grant select on public.posts, public.comments, public.likes, public.follows, public.items, public.submissions to anon, authenticated;
grant insert, delete on public.posts, public.comments, public.likes, public.follows, public.items, public.submissions to authenticated;
grant update (caption, kind, ask) on public.posts to authenticated;
grant update (status, ask) on public.items to authenticated;
grant update (status) on public.submissions to authenticated;

grant select, insert on public.messages to authenticated;
grant update (read_at) on public.messages to authenticated;

revoke execute on function public.is_admin() from public, anon;
grant execute on function public.is_admin() to authenticated;
revoke execute on function public.handle_new_user() from public, anon, authenticated;

-- ---------- live messages ----------
do $$ begin
  if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'messages') then
    alter publication supabase_realtime add table public.messages;
  end if;
end $$;

-- ---------- photo storage (public bucket, 2 MB images) ----------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('photos', 'photos', true, 2097152, array['image/jpeg', 'image/png', 'image/webp'])
on conflict (id) do update set public = true, file_size_limit = 2097152, allowed_mime_types = array['image/jpeg', 'image/png', 'image/webp'];

drop policy if exists "upload own photos" on storage.objects;
create policy "upload own photos" on storage.objects for insert to authenticated
  with check (bucket_id = 'photos' and (storage.foldername(name))[1] = (select auth.uid())::text);
drop policy if exists "delete own photos" on storage.objects;
create policy "delete own photos" on storage.objects for delete to authenticated
  using (bucket_id = 'photos' and (storage.foldername(name))[1] = (select auth.uid())::text);

-- =====================================================================
-- After you create your own account on the site, make yourself the
-- moderator (lets you approve scanned cards). Replace the handle and run:
--
--   update public.profiles set is_admin = true where lower(handle) = lower('YourHandle');
-- =====================================================================
