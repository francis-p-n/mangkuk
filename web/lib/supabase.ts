import { createClient } from "@supabase/supabase-js";
import type { Result } from "./format";

// The anon key, and only the anon key. Row-level security makes it read-only
// (see supabase/migrations/0001_results.sql), so it is safe in the browser -
// but every query here runs on the server anyway, which keeps the round trip
// to one and the payload to the rows a page actually shows.
//
// Read through a computed key, at call time, on purpose. Next inlines every
// literal `process.env.NEXT_PUBLIC_X` it can see into the bundle when the
// build runs, so a variable added afterwards is baked in as undefined and
// setting it changes nothing until the next build - which looks exactly like
// setting it wrong. A computed lookup cannot be inlined, so the value is read
// from the running server and a redeploy is enough.
function env(name: string): string | undefined {
  const raw = process.env[name];
  const v = raw?.trim();
  return v ? v : undefined;
}

// Supabase renamed the browser-side key: projects created before the change
// hand you an "anon key", newer ones a "publishable key". They go in the same
// place and do the same job, and a project is issued only one of the two - so
// both names are accepted rather than making the reader discover which
// vocabulary their dashboard uses.
const URL_NAMES = ["SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL"];
const KEY_NAMES = [
  "SUPABASE_ANON_KEY",
  "SUPABASE_PUBLISHABLE_KEY",
  "NEXT_PUBLIC_SUPABASE_ANON_KEY",
  "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
];

/** Unprefixed first: those are never inlined, so they always mean runtime. */
function settings() {
  const first = (names: string[]) =>
    names.map(env).find((v) => v !== undefined);
  return { url: first(URL_NAMES), anon: first(KEY_NAMES) };
}

export class NotConfigured extends Error {
  /** Which ones are missing, because "not configured" does not say. */
  readonly missing: string[];

  constructor(missing: string[]) {
    super(`not set: ${missing.join(", ")}`);
    this.name = "NotConfigured";
    this.missing = missing;
  }
}

export function db() {
  const { url, anon } = settings();
  const missing = [
    ...(url ? [] : [URL_NAMES.join(" or ")]),
    ...(anon ? [] : ["NEXT_PUBLIC_SUPABASE_ANON_KEY (or …PUBLISHABLE_KEY)"]),
  ];
  if (!url || !anon) throw new NotConfigured(missing);
  return createClient(url, anon, { auth: { persistSession: false } });
}

export type Labels = {
  category?: Record<string, string>;
  category_blurb?: Record<string, string>;
  status?: Record<string, string>;
  tone?: Record<string, string>;
  reason?: Record<string, string>;
  field?: Record<string, string>;
  band?: Record<string, string>;
  band_blurb?: Record<string, string>;
};

export type Run = {
  id: string;
  generated_at: string;
  source: string | null;
  totals: {
    emails: number;
    comparisons: number;
    mismatch: number;
    review: number;
    ok: number;
  };
  labels: Labels;
  bands: { name: string; consequence: string }[];
  severity: Record<string, number>;
};

/** The run the site is serving. Null when nothing has been loaded yet. */
export async function currentRun(): Promise<Run | null> {
  const { data, error } = await db()
    .from("runs")
    .select("id, generated_at, source, totals, labels, bands, severity")
    .eq("is_current", true)
    .maybeSingle();
  if (error) throw new Error(`reading the current run: ${error.message}`);
  return (data as Run) ?? null;
}

// Everything, for the one shipment being read in detail.
const COLUMNS =
  "email_id, category, rule, status, review_reason, has_defect, defect_fields, " +
  "subject, sender, body, oc_number, booking_ref, note, severity, " +
  "severity_field, " +
  "severity_reason, documents, comparisons, shipment";

// What a row in a list actually draws, and nothing else.
//
// The full set was being fetched for every row of every list: seven
// comparisons and two document records per shipment, none of which a list
// renders. On an unfiltered search that was five hundred rows of it - 1.4MB
// and four seconds to draw a list of names and ports. The detail panel reads
// the whole row separately, so nothing on screen loses anything.
//
// `category` is the one addition that is not drawn. It is what separates a
// draft that was checked and matched from an instruction request that was
// never checked at all - both of which the pipeline stores as `OK`. Without it
// a list cannot tell the two apart, and 391 emails that nobody compared were
// being labelled "Everything matches".
const LIST_COLUMNS =
  "email_id, category, status, review_reason, defect_fields, subject, " +
  "oc_number, booking_ref, severity, shipment";

/** A row as a list needs it. The heavy JSONB is deliberately absent. */
export type ListRow = Pick<
  Result,
  | "email_id"
  | "category"
  | "status"
  | "review_reason"
  | "defect_fields"
  | "subject"
  | "oc_number"
  | "booking_ref"
  | "severity"
  | "shipment"
>;

/** Worst first, the order the queue is meant to be worked in. */
const BAND_ORDER = ["critical", "serious", "routine"];

function worstFirst<T extends { severity: string | null; email_id: string }>(
  rows: T[]
): T[] {
  return [...rows].sort((a, b) => {
    const ai = a.severity ? BAND_ORDER.indexOf(a.severity) : 99;
    const bi = b.severity ? BAND_ORDER.indexOf(b.severity) : 99;
    if (ai !== bi) return ai - bi;
    return a.email_id.localeCompare(b.email_id);
  });
}

/**
 * A verdict belongs to a document check and to nothing else.
 *
 * The pipeline gives every email a status, and an email it never compared
 * keeps the default `OK`. Filtering on status alone therefore returns the 391
 * instruction requests, invoice questions and berthing reports alongside the
 * 63 drafts that genuinely matched - under a heading that says "Fine".
 */
const COMPARISON = "BL_COMPARISON";

export async function byStatus(
  runId: string,
  status: Result["status"]
): Promise<ListRow[]> {
  const { data, error } = await db()
    .from("results")
    .select(LIST_COLUMNS)
    .eq("run_id", runId)
    .eq("category", COMPARISON)
    .eq("status", status);
  if (error) throw new Error(`reading ${status}: ${error.message}`);
  return worstFirst((data ?? []) as unknown as ListRow[]);
}

/** Postgres: the column named in the query does not exist on the table. */
const UNDEFINED_COLUMN = "42703";

export async function one(
  runId: string,
  emailId: string
): Promise<Result | null> {
  const read = (columns: string) =>
    db()
      .from("results")
      .select(columns)
      .eq("run_id", runId)
      .eq("email_id", emailId)
      .maybeSingle();

  let { data, error } = await read(COLUMNS);

  // `body` arrived in migration 0002, and code reaches a deployment before a
  // migration does. Asking for a column the table has not got fails the whole
  // select, which would blank the detail panel over a field that is merely
  // nice to have - so on that one error, ask again without it and show the
  // shipment. The email section is absent until the migration lands, and
  // nothing else notices.
  if (error?.code === UNDEFINED_COLUMN && COLUMNS.includes("body")) {
    ({ data, error } = await read(COLUMNS.replace("body, ", "")));
  }

  if (error) throw new Error(`reading ${emailId}: ${error.message}`);
  return (data as unknown as Result) ?? null;
}

/**
 * The search the clerk actually does: a customer, an OC number, a port, a
 * vessel. Postgres does the filtering, so a 520-row run and a 50,000-row one
 * cost the browser the same.
 */
export async function search(
  runId: string,
  {
    q,
    status,
    from,
    to,
  }: { q?: string; status?: string; from?: string; to?: string }
): Promise<ListRow[]> {
  let query = db().from("results").select(LIST_COLUMNS).eq("run_id", runId);

  // Same rule as byStatus: asking for "Fine" means asking for drafts that were
  // checked and matched, not for every email the pipeline left at its default.
  if (status && status !== "ALL") {
    query = query.eq("category", COMPARISON).eq("status", status);
  }

  // Postgres does the narrowing, same as the status filter. A country is
  // matched inside the port string rather than against a stored column,
  // because the port already carries it and a second copy would be a second
  // thing to keep true.
  if (from) query = query.ilike("shipment->>port_of_loading", `%${from}%`);
  if (to) query = query.ilike("shipment->>port_of_discharge", `%${to}%`);

  if (q && q.trim()) {
    // ilike across the columns a person types into, plus the shipment JSON so
    // a vessel or port name finds its shipment. Escaped for PostgREST's
    // comma-separated or() syntax, where a bare comma would split the filter.
    const term = q.trim().replace(/[%,()]/g, " ");
    query = query.or(
      [
        `subject.ilike.%${term}%`,
        `oc_number.ilike.%${term}%`,
        `booking_ref.ilike.%${term}%`,
        `sender.ilike.%${term}%`,
        `shipment->>consignee.ilike.%${term}%`,
        `shipment->>shipper.ilike.%${term}%`,
        `shipment->>vessel.ilike.%${term}%`,
        `shipment->>port_of_loading.ilike.%${term}%`,
        `shipment->>port_of_discharge.ilike.%${term}%`,
      ].join(",")
    );
  }

  const { data, error } = await query.limit(PAGE);
  if (error) throw new Error(`searching: ${error.message}`);
  return worstFirst((data ?? []) as unknown as ListRow[]);
}

/**
 * How many rows one search returns.
 *
 * A cap, not a count. The caller has to say so when it is hit, because
 * "100 of 520 match" reads as a filter that excluded four hundred shipments
 * when it actually means four hundred were never fetched.
 *
 * A hundred rather than five hundred because the cost here is the markup, not
 * the query: every row is about 2.5KB of HTML and the same again in the
 * payload that hydrates it, so five hundred of them was 1.3MB and two seconds
 * before anything appeared. The queues a clerk actually opens - 46 needing a
 * fix, 20 needing a look - are well inside this, so only the unfiltered
 * "Everything" view truncates, and it says so.
 */
export const PAGE = 100;
