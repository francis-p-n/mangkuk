-- The desk's run, as a table.
--
-- One row per email, which is the grain the whole UI works in: every page
-- either lists these or opens one of them. The four nested structures stay
-- JSONB rather than becoming child tables - they are read whole, written
-- whole, and never queried across, so splitting them would buy joins and
-- cost the thing that makes a shipment card one round trip.
--
-- Scalars that the UI filters or sorts by are columns, so the index can be
-- used. Everything else rides along in JSONB.

create table if not exists public.results (
    email_id         text primary key,
    run_id           uuid not null,

    category         text not null,
    rule             text,
    status           text not null check (status in ('OK', 'MISMATCH', 'NEEDS_REVIEW')),
    review_reason    text check (review_reason in
                        ('wrong_doc_type', 'missing_attachment',
                         'unreadable', 'missing_value')),
    has_defect       boolean not null default false,
    defect_fields    text[] not null default '{}',

    subject          text,
    sender           text,
    oc_number        text,
    booking_ref      text,
    note             text,

    severity         text,
    severity_field   text,
    severity_reason  text,

    documents        jsonb not null default '[]'::jsonb,
    comparisons      jsonb not null default '[]'::jsonb,
    shipment         jsonb not null default '{}'::jsonb,

    -- The same contradictions validate.py refuses to submit, refused here
    -- too. A row that says OK while naming defect fields is wrong wherever
    -- it is stored, and the database is the last place it can be caught.
    constraint defect_matches_status
        check (has_defect = (status = 'MISMATCH')),
    constraint mismatch_names_fields
        check (status <> 'MISMATCH' or cardinality(defect_fields) > 0),
    constraint clean_names_nothing
        check (status = 'MISMATCH' or cardinality(defect_fields) = 0),
    constraint reason_iff_review
        check ((status = 'NEEDS_REVIEW') = (review_reason is not null))
);

-- One row per pipeline run, so a load is atomic: write the new run, point
-- the pointer at it, and the old rows can go. Without this a half-finished
-- load is a half-finished site.
create table if not exists public.runs (
    id            uuid primary key default gen_random_uuid(),
    generated_at  timestamptz not null default now(),
    source        text,
    totals        jsonb not null default '{}'::jsonb,
    is_current    boolean not null default false
);

create unique index if not exists runs_one_current
    on public.runs (is_current) where is_current;

alter table public.results
    drop constraint if exists results_run_id_fkey;
alter table public.results
    add constraint results_run_id_fkey
    foreign key (run_id) references public.runs (id) on delete cascade;

create index if not exists results_status    on public.results (status);
create index if not exists results_category  on public.results (category);
create index if not exists results_severity  on public.results (severity);
create index if not exists results_run       on public.results (run_id);

-- Text search over the fields a clerk actually types into the search box.
create index if not exists results_search on public.results
    using gin (to_tsvector('simple',
        coalesce(subject, '') || ' ' ||
        coalesce(oc_number, '') || ' ' ||
        coalesce(booking_ref, '') || ' ' ||
        coalesce(sender, '')));

-- Read-only to the world, writable only by the service role.
--
-- The site has no accounts - its sign-in page is a prototype that accepts
-- anything - so anon can read. It must never write: the pipeline is the only
-- author, and a browser that can edit a verdict makes the whole run
-- unciteable. The loader uses the service key, which bypasses RLS.
alter table public.results enable row level security;
alter table public.runs    enable row level security;

drop policy if exists results_read on public.results;
create policy results_read on public.results for select to anon, authenticated using (true);

drop policy if exists runs_read on public.runs;
create policy runs_read on public.runs for select to anon, authenticated using (true);
