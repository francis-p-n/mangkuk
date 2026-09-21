import { db } from "./supabase";
import type { ListRow } from "./supabase";
import type { Result } from "./format";
import {
  componentsOf,
  foldFolder,
  groupRows,
  referenceOf,
  referencesOf,
  shipmentKey,
  byEmailId,
} from "./graph";
import type { Folder } from "./graph";

/**
 * A shipment, and the mail about it.
 *
 * The grain of this product is the shipment, not the message. A desk does not
 * think "email 004"; it thinks "the Karachi box for Linden & Hale", and the
 * correspondence about it is a folder, not a queue position. One draft gets
 * checked, chased, corrected and confirmed across four messages, and all four
 * belong together.
 *
 * The grouping rules themselves live in `graph.ts`, which imports nothing, so
 * a test runner can reach them without a database. This file is the part that
 * talks to Postgres.
 */

export {
  componentsOf,
  decisiveEmail,
  foldFolder,
  isComparison,
  referenceOf,
  referencesOf,
  shipmentKey,
} from "./graph";
export type { Folder, FoldRow, GraphRow } from "./graph";

export type Shipment = Folder<ListRow>;

/** Fold rows into folders, worst first. */
export function groupIntoShipments(rows: ListRow[]): Shipment[] {
  return groupRows(rows);
}

/**
 * A folder row carries the sender as well, because a thread is read by who
 * said what. Declared rather than borrowed from ListRow so the type says what
 * the query below actually selects.
 */
export type FolderRow = ListRow & { sender: string | null };

const FOLDER_COLUMNS =
  "email_id, category, status, review_reason, defect_fields, subject, sender, " +
  "oc_number, booking_ref, severity, shipment";

/** Just enough of a row to build the reference graph from. */
const EDGE_COLUMNS = "email_id, oc_number, booking_ref, shipment";

type EdgeRow = {
  email_id: string;
  oc_number: string | null;
  booking_ref: string | null;
  shipment?: { bl_number?: string | null } | null;
};

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
    .select(EDGE_COLUMNS)
    .eq("run_id", runId)
    .limit(20000);
  if (e1) throw new Error(`reading the reference graph: ${e1.message}`);

  const rows = (edges ?? []) as unknown as EdgeRow[];
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

  return ((data ?? []) as unknown as FolderRow[]).sort(byEmailId);
}

/** The state one open folder carries, from the rows the page already has. */
export function folderState(emails: FolderRow[]): Folder<FolderRow> | null {
  return emails.length ? foldFolder(emails) : null;
}

export { shipmentKey as keyOf, referenceOf as refOf };
export type { Result };
