import { db } from "./supabase";
import type { ListRow } from "./supabase";
import type { Result } from "./format";

/**
 * A shipment, and the mail about it.
 *
 * The grain of this product is the shipment, not the message. A desk does not
 * think "email 004"; it thinks "the Karachi box for Linden & Hale", and the
 * correspondence about it is a folder, not a queue position. One draft gets
 * checked, chased, corrected and confirmed across four messages, and all four
 * belong together.
 *
 * WHAT GROUPS, AND WHAT DOES NOT
 *
 * A shared reference groups. Shared details never do.
 *
 * That rule is not caution for its own sake - it is the one thing the corpus
 * has to say on the subject. Exactly one pair of emails in 520 shares a
 * consignee, a lane and a container size: email_468 and email_502, both
 * Roxcel to Ashdod, one 40'HC. They carry different OC numbers and are
 * different shipments. Matching on details would have filed them as one, and a
 * clerk would then be reading one shipment's mail while acting on another's -
 * which is the exact failure this product exists to prevent, committed by the
 * product itself.
 *
 * So details may corroborate a reference and may suggest a link for a person
 * to confirm. They may not create one.
 */

/** What files an email. Null when it carries no reference at all. */
export function referenceOf(r: {
  oc_number: string | null;
  booking_ref: string | null;
}): string | null {
  return r.oc_number?.trim() || r.booking_ref?.trim() || null;
}

/**
 * The references an email carries. Each one is an edge.
 */
export function referencesOf(r: {
  oc_number: string | null;
  booking_ref: string | null;
}): string[] {
  return [r.oc_number?.trim(), r.booking_ref?.trim()].filter(
    (v): v is string => Boolean(v)
  );
}

/**
 * Emails are vertices, references are edges, and a shipment is a connected
 * component.
 *
 * Picking one reference per email and grouping on it is not the same thing,
 * and the difference is a real thread cut in half. An email carrying both an
 * OC number and a booking is a bridge: anything sharing either reference
 * belongs to the same shipment, even when two of those emails share nothing
 * with each other directly. 213 of 520 emails here carry both, so the bridge
 * case is structural rather than hypothetical - it simply never fires on this
 * corpus, where no reference repeats at all.
 *
 * An email carrying no reference is an isolated vertex and therefore its own
 * component: a file of one. 123 of 520 are like this - billing notices,
 * berthing reports, a time-off request. Filing them together under "no
 * reference" would make one folder of a hundred unrelated things, which is
 * the filing cabinet this product replaces.
 *
 * What is deliberately *not* an edge: a shared consignee, lane or container
 * size. Exactly one pair in this corpus shares all three - email_468 and
 * email_502, both Roxcel to Ashdod, one 40'HC - and they carry different OC
 * numbers and are different shipments. An edge drawn on resemblance would
 * have merged them, and a clerk would be reading one shipment's mail while
 * acting on another's.
 */
class Components {
  private parent = new Map<string, string>();

  private find(x: string): string {
    let root = this.parent.get(x) ?? x;
    if (root === x) {
      this.parent.set(x, x);
      return x;
    }
    root = this.find(root);
    this.parent.set(x, root);      // path compression
    return root;
  }

  union(a: string, b: string) {
    const ra = this.find(a);
    const rb = this.find(b);
    if (ra !== rb) this.parent.set(ra, rb);
  }

  add(x: string) {
    this.find(x);
  }

  rootOf(x: string): string {
    return this.find(x);
  }
}

/** Build the graph, and return which component each email lands in. */
export function componentsOf(
  rows: { email_id: string; oc_number: string | null; booking_ref: string | null }[]
): Map<string, string> {
  const g = new Components();
  for (const r of rows) {
    const v = `email:${r.email_id}`;
    g.add(v);
    // Reference vertices are namespaced so a booking that happens to read
    // like an email id cannot collide with one.
    for (const ref of referencesOf(r)) g.union(v, `ref:${ref}`);
  }

  const out = new Map<string, string>();
  for (const r of rows) out.set(r.email_id, g.rootOf(`email:${r.email_id}`));
  return out;
}

/** What a component is called: its reference, or the lone email's id. */
export function shipmentKey(r: {
  email_id: string;
  oc_number: string | null;
  booking_ref: string | null;
}): string {
  return referencesOf(r)[0] ?? r.email_id;
}

export type Shipment = {
  key: string;
  reference: string | null;
  emails: ListRow[];
  /** The verdict the folder currently carries. */
  status: ListRow["status"];
  severity: string | null;
  /** True once a later comparison came back clean on a folder that had failed. */
  resolved: boolean;
};

const RANK: Record<string, number> = { MISMATCH: 0, NEEDS_REVIEW: 1, OK: 2 };

/**
 * Fold rows into folders.
 *
 * The folder's state is the state of its *latest* comparison, not the worst
 * one it has ever held - a shipment that was wrong on Monday and right on
 * Thursday is right. That is the whole point of filing the thread together,
 * and the reason a mismatch can finally stop being true.
 *
 * Email ids sort chronologically in this corpus, which is what "latest" leans
 * on. Real mail would carry a date and this would use it.
 */
export function groupIntoShipments(rows: ListRow[]): Shipment[] {
  const component = componentsOf(rows);
  const folders = new Map<string, ListRow[]>();
  for (const r of rows) {
    const k = component.get(r.email_id) ?? `email:${r.email_id}`;
    folders.set(k, [...(folders.get(k) ?? []), r]);
  }

  const out: Shipment[] = [];
  for (const [, emails] of folders) {
    const sorted = [...emails].sort((a, b) =>
      a.email_id.localeCompare(b.email_id)
    );
    const comparisons = sorted.filter((e) => e.status !== "OK" || e.severity);
    const latest = sorted[sorted.length - 1];
    const decisive = comparisons[comparisons.length - 1] ?? latest;

    // Was there an earlier failure that a later message cleared?
    const everFailed = sorted.some((e) => e.status === "MISMATCH");
    const resolved = everFailed && decisive.status === "OK";

    out.push({
      key: shipmentKey(sorted[0]),
      reference: referenceOf(sorted[0]),
      emails: sorted,
      status: decisive.status,
      severity: decisive.severity,
      resolved,
    });
  }

  return out.sort((a, b) => {
    const r = (RANK[a.status] ?? 9) - (RANK[b.status] ?? 9);
    return r !== 0 ? r : a.key.localeCompare(b.key);
  });
}

/**
 * A folder row carries the sender as well, because a thread is read by who
 * said what. Declared rather than borrowed from ListRow so the type says what
 * the query below actually selects.
 */
export type FolderRow = ListRow & { sender: string | null };

const FOLDER_COLUMNS =
  "email_id, status, review_reason, defect_fields, subject, sender, " +
  "oc_number, booking_ref, severity, shipment";

/**
 * Every email in the same component as this reference, oldest first.
 *
 * Two queries rather than one, and the reason is transitivity. `oc = X or
 * booking = X` finds the emails that name X themselves; it does not find the
 * email that shares only a booking with one of *those*. The component is what
 * the folder is, so the graph has to be built before it can be asked.
 *
 * The first query fetches two short strings per row - about 30KB for a
 * 520-row run - rather than storing a component id that would need a
 * migration and could go stale against the rows it describes.
 */
export async function folderFor(
  runId: string,
  reference: string
): Promise<FolderRow[]> {
  const { data: edges, error: e1 } = await db()
    .from("results")
    .select("email_id, oc_number, booking_ref")
    .eq("run_id", runId)
    .limit(20000);
  if (e1) throw new Error(`reading the reference graph: ${e1.message}`);

  const rows = (edges ?? []) as unknown as {
    email_id: string;
    oc_number: string | null;
    booking_ref: string | null;
  }[];
  const component = componentsOf(rows);

  // The reference may name a shipment, or be the id of an email that carries
  // no reference at all and is therefore its own component.
  const seed =
    rows.find((r) => referencesOf(r).includes(reference)) ??
    rows.find((r) => r.email_id === reference);
  if (!seed) return [];

  const root = component.get(seed.email_id);
  const ids = rows
    .filter((r) => component.get(r.email_id) === root)
    .map((r) => r.email_id);
  if (!ids.length) return [];

  const { data, error } = await db()
    .from("results")
    .select(FOLDER_COLUMNS)
    .eq("run_id", runId)
    .in("email_id", ids)
    .limit(500);
  if (error) throw new Error(`reading folder ${reference}: ${error.message}`);

  return ((data ?? []) as unknown as FolderRow[]).sort((a, b) =>
    a.email_id.localeCompare(b.email_id)
  );
}

/** The email in a folder whose comparison decides its current state. */
export function decisiveEmail<T extends { email_id: string; defect_fields: string[]; severity: string | null }>(
  emails: T[]
): T | null {
  if (!emails.length) return null;
  const withVerdict = emails.filter((e) => e.defect_fields?.length || e.severity);
  return withVerdict[withVerdict.length - 1] ?? emails[emails.length - 1];
}

export type { Result };
