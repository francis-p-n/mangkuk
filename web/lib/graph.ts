/**
 * The shipment graph, and the verdict a file carries.
 *
 * Pure: no imports, no database, no React. That is the point of the file
 * rather than an accident of it. The grouping rules used to live inside
 * `shipments.ts`, which reaches Supabase on load, so the only way to test them
 * was to write a second copy of the algorithm somewhere a test could reach -
 * which is exactly what `tests/test_grouping.py` did, and the two had already
 * drifted apart (the copy never learned about B/L numbers). Everything here is
 * importable by a test runner with nothing else running, so there is one
 * implementation and the tests are pointed at it.
 *
 * EMAILS ARE VERTICES, REFERENCES ARE EDGES, A SHIPMENT IS A COMPONENT
 *
 * A shared reference groups. Shared details never do.
 *
 * That rule is the one thing the corpus has to say on the subject. Exactly one
 * pair of emails in 520 shares a consignee, a lane and a container size:
 * email_468 and email_502, both Roxcel to Ashdod, one 40'HC. They carry
 * different OC numbers and are different shipments. Matching on details would
 * have filed them as one, and a clerk would then be reading one shipment's
 * mail while acting on another's - the exact failure this product exists to
 * prevent, committed by the product itself.
 */

export type Status = "OK" | "MISMATCH" | "NEEDS_REVIEW";

/** The category the pipeline assigns. Only one of them carries a verdict. */
export const COMPARISON = "BL_COMPARISON";

/** What the graph needs from a row: an identity and its references. */
export type GraphRow = {
  email_id: string;
  oc_number: string | null;
  booking_ref: string | null;
  shipment?: { bl_number?: string | null } | null;
};

/** What the fold needs on top of that: what kind of mail, and its verdict. */
export type FoldRow = GraphRow & {
  category?: string | null;
  status: Status;
  severity: string | null;
};

/**
 * Was this email a document check?
 *
 * The distinction the rest of this file turns on. The pipeline gives every
 * email a `status`, and an email that was never compared gets `OK` - not
 * because anything matched but because nothing was asked. Reading that `OK` as
 * a verdict is how an instruction request ends up labelled "Everything
 * matches", and how a corrected shipment fails to notice it was corrected.
 *
 * Rows loaded before `category` was carried into list queries have it
 * undefined. Treating those as comparisons keeps the old behaviour rather than
 * silently emptying every queue against a stale table.
 */
export function isComparison(r: { category?: string | null }): boolean {
  return r.category === undefined || r.category === null || r.category === COMPARISON;
}

/**
 * The references an email carries. Each one is an edge.
 *
 * Three names for one shipment, the way a note can have aliases: the OC number
 * the desk files under, the booking the carrier quotes, and the B/L number
 * printed on the draft itself. A carrier replying about a document usually
 * quotes the B/L and nothing else, so leaving it out cuts the commonest real
 * thread-join there is - even though only ten emails here carry one and none
 * of them repeats.
 */
export function referencesOf(r: GraphRow): string[] {
  return [
    r.oc_number?.trim(),
    r.booking_ref?.trim(),
    r.shipment?.bl_number?.trim(),
  ].filter((v): v is string => Boolean(v));
}

/** What files an email. Null when it carries no reference at all. */
export function referenceOf(r: GraphRow): string | null {
  return referencesOf(r)[0] ?? null;
}

/** What a component is called: its reference, or the lone email's id. */
export function shipmentKey(r: GraphRow): string {
  return referencesOf(r)[0] ?? r.email_id;
}

/** Email ids sort chronologically in this corpus, which is what order means. */
export function byEmailId(a: { email_id: string }, b: { email_id: string }): number {
  return a.email_id.localeCompare(b.email_id);
}

/**
 * Union-find over emails and the references they carry.
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
 * reference" would make one folder of a hundred unrelated things, which is the
 * filing cabinet this product replaces.
 */
export function componentsOf(rows: GraphRow[]): Map<string, string> {
  const parent = new Map<string, string>();

  const find = (x: string): string => {
    let root = parent.get(x) ?? x;
    if (root === x) {
      parent.set(x, x);
      return x;
    }
    root = find(root);
    parent.set(x, root); // path compression
    return root;
  };

  const union = (a: string, b: string): void => {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent.set(ra, rb);
  };

  for (const r of rows) {
    const v = `email:${r.email_id}`;
    find(v);
    // Reference vertices are namespaced so a booking that happens to read like
    // an email id cannot collide with one.
    for (const ref of referencesOf(r)) union(v, `ref:${ref}`);
  }

  const out = new Map<string, string>();
  for (const r of rows) out.set(r.email_id, find(`email:${r.email_id}`));
  return out;
}

export type Folder<T> = {
  key: string;
  reference: string | null;
  /** Oldest first. */
  emails: T[];
  /** Is there a document check in this file at all? */
  checked: boolean;
  /** The verdict the file carries, or null when nothing was ever compared. */
  status: Status | null;
  severity: string | null;
  /** The comparison that decides the file's state, or null when there is none. */
  decisive: T | null;
  /** A check failed here once, and the latest one came back clean. */
  resolved: boolean;
};

/**
 * The comparison that decides a file's state: the latest one, full stop.
 *
 * Not the latest *failure*, which is what this used to be, and the difference
 * was the whole feature. A file is a thread - one draft checked, chased,
 * corrected and confirmed - and the state of the thread is the state of its
 * last check. Filtering the clean checks out before choosing (`status !== "OK"
 * || severity`) left a set that could only ever end on a failure, so the
 * `resolved` flag downstream of it was unreachable: a shipment that was wrong
 * on Monday and right on Thursday still read "needs fixing" on Friday, and the
 * panel opened the Monday draft.
 *
 * Non-comparison mail is skipped rather than allowed to be decisive, because
 * its `OK` is an absence of a question, not an answer to one.
 */
export function decisiveEmail<T extends FoldRow>(emails: T[]): T | null {
  const comparisons = emails.filter(isComparison);
  return comparisons[comparisons.length - 1] ?? null;
}

/** Fold one file's emails into the state it currently carries. */
export function foldFolder<T extends FoldRow>(emails: T[]): Folder<T> {
  const sorted = [...emails].sort(byEmailId);
  const comparisons = sorted.filter(isComparison);
  const decisive = comparisons[comparisons.length - 1] ?? null;
  const everFailed = comparisons.some((e) => e.status === "MISMATCH");

  return {
    key: shipmentKey(sorted[0]),
    reference: referenceOf(sorted[0]),
    emails: sorted,
    checked: comparisons.length > 0,
    status: decisive ? decisive.status : null,
    severity: decisive ? decisive.severity : null,
    decisive,
    resolved: everFailed && decisive?.status === "OK",
  };
}

/** Worst first, then unchecked files, then alphabetical within a band. */
const RANK: Record<string, number> = { MISMATCH: 0, NEEDS_REVIEW: 1, OK: 2 };
const UNCHECKED = 3;

/**
 * Fold rows into files.
 *
 * Every shipment is a file, whatever state it is in. A clean draft is not an
 * absence of work - it is a container with paperwork that agrees, and a clerk
 * asked for "the Karachi box" wants it whether or not it once needed chasing.
 */
export function groupRows<T extends FoldRow>(rows: T[]): Folder<T>[] {
  const component = componentsOf(rows);
  const files = new Map<string, T[]>();
  for (const r of rows) {
    const k = component.get(r.email_id) ?? `email:${r.email_id}`;
    files.set(k, [...(files.get(k) ?? []), r]);
  }

  const out = [...files.values()].map(foldFolder);
  return out.sort((a, b) => {
    const ra = a.status ? RANK[a.status] ?? UNCHECKED : UNCHECKED;
    const rb = b.status ? RANK[b.status] ?? UNCHECKED : UNCHECKED;
    return ra !== rb ? ra - rb : a.key.localeCompare(b.key);
  });
}
