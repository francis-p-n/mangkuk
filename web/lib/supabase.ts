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

const COLUMNS =
  "email_id, category, rule, status, review_reason, has_defect, defect_fields, " +
  "subject, sender, oc_number, booking_ref, note, severity, severity_field, " +
  "severity_reason, documents, comparisons, shipment";

/** Worst first, the order the queue is meant to be worked in. */
const BAND_ORDER = ["critical", "serious", "routine"];

function worstFirst(rows: Result[]): Result[] {
  return [...rows].sort((a, b) => {
    const ai = a.severity ? BAND_ORDER.indexOf(a.severity) : 99;
    const bi = b.severity ? BAND_ORDER.indexOf(b.severity) : 99;
    if (ai !== bi) return ai - bi;
    return a.email_id.localeCompare(b.email_id);
  });
}

export async function byStatus(
  runId: string,
  status: Result["status"]
): Promise<Result[]> {
  const { data, error } = await db()
    .from("results")
    .select(COLUMNS)
    .eq("run_id", runId)
    .eq("status", status);
  if (error) throw new Error(`reading ${status}: ${error.message}`);
  return worstFirst((data ?? []) as unknown as Result[]);
}

export async function one(
  runId: string,
  emailId: string
): Promise<Result | null> {
  const { data, error } = await db()
    .from("results")
    .select(COLUMNS)
    .eq("run_id", runId)
    .eq("email_id", emailId)
    .maybeSingle();
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
  { q, status }: { q?: string; status?: string }
): Promise<Result[]> {
  let query = db().from("results").select(COLUMNS).eq("run_id", runId);

  if (status && status !== "ALL") query = query.eq("status", status);

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
  return worstFirst((data ?? []) as unknown as Result[]);
}

/**
 * How many rows one search returns.
 *
 * A cap, not a count. The caller has to say so when it is hit, because
 * "500 of 520 match" reads as a filter that excluded twenty shipments when
 * it actually means twenty were never fetched.
 */
export const PAGE = 500;
