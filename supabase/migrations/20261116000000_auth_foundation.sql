-- Accounts live in Supabase-managed auth.users; do not recreate that schema.
-- Future user-data tables (S16.2) must opt in to Data API access explicitly,
-- alongside ENABLE ROW LEVEL SECURITY and reviewed owner policies.
-- Existing tables/grants from the old sample-data experiment are not changed.
revoke create on schema public from public;

alter default privileges for role postgres in schema public
    revoke all on tables from anon, authenticated;
alter default privileges for role postgres in schema public
    revoke all on sequences from anon, authenticated;
alter default privileges for role postgres in schema public
    revoke execute on functions from public, anon, authenticated;
