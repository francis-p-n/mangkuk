-- The message itself.
--
-- A verdict about an email is easier to trust when the email is one click
-- away. Until now the site showed what the checker concluded and the clerk had
-- to go back to their mailbox to see what was actually asked.
--
-- A column rather than a table: it is read only when one shipment is open,
-- written once with the row, and never queried across. The list queries do not
-- select it, so a page of a hundred rows does not carry a hundred bodies.
--
-- Safe to run on a table that already has rows: the column is nullable, so
-- existing rows keep whatever they have and the next load fills them in.

alter table public.results
    add column if not exists body text;

comment on column public.results.body is
    'The email body as received. Shown in the detail panel only.';
