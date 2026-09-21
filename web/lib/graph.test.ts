/**
 * The grouping rules, tested against the code that ships.
 *
 *     npm test --prefix web
 *
 * This file exists because the previous arrangement did not test anything
 * that ran. `tests/test_grouping.py` carried its own copy of the union-find
 * and asserted against that, so the shipped `componentsOf` had no coverage at
 * all: removing bridging from it left every one of the 435 Python tests green
 * and the typecheck clean. The copy had also drifted - it never learned that
 * a B/L number is an edge.
 *
 * Node runs TypeScript directly (type stripping, v22.6+), so this needs no
 * build step and no test framework. `graph.ts` imports nothing, which is what
 * makes that possible.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  componentsOf,
  decisiveEmail,
  fileKey,
  foldFolder,
  groupRows,
  isComparison,
  referenceOf,
  referencesOf,
  shipmentKey,
} from "./graph.ts";
import type { FoldRow, GraphRow, Status } from "./graph.ts";

// ------------------------------------------------------------------ builders

function email(
  id: string,
  refs: { oc?: string; booking?: string; bl?: string } = {}
): GraphRow {
  return {
    email_id: id,
    oc_number: refs.oc ?? null,
    booking_ref: refs.booking ?? null,
    shipment: refs.bl ? { bl_number: refs.bl } : null,
  };
}

function check(
  id: string,
  status: Status,
  refs: { oc?: string; booking?: string; bl?: string } = {},
  severity: string | null = null
): FoldRow {
  return {
    ...email(id, refs),
    category: "BL_COMPARISON",
    status,
    severity: severity ?? (status === "MISMATCH" ? "critical" : null),
  };
}

/** Mail that is not a document check. The pipeline stores it as OK. */
function other(
  id: string,
  category: string,
  refs: { oc?: string; booking?: string; bl?: string } = {}
): FoldRow {
  return { ...email(id, refs), category, status: "OK", severity: null };
}

const folders = (rows: GraphRow[]): string[][] => {
  const comp = componentsOf(rows);
  const out = new Map<string, string[]>();
  for (const r of rows) {
    const k = comp.get(r.email_id)!;
    out.set(k, [...(out.get(k) ?? []), r.email_id]);
  }
  return [...out.values()].map((ids) => ids.sort()).sort((a, b) =>
    a[0].localeCompare(b[0])
  );
};

// ------------------------------------------------------------- the reference

test("an email with no reference is its own file", () => {
  assert.deepEqual(folders([email("email_001"), email("email_002")]), [
    ["email_001"],
    ["email_002"],
  ]);
});

test("unreferenced emails are never filed together", () => {
  // Otherwise 123 unrelated notices become one folder.
  const rows = [1, 2, 3, 4, 5].map((i) => email(`email_00${i}`));
  const got = folders(rows);
  assert.equal(got.length, 5);
  assert.ok(got.every((f) => f.length === 1));
});

test("a shared OC number groups", () => {
  assert.deepEqual(
    folders([email("a", { oc: "OC-1" }), email("b", { oc: "OC-1" })]),
    [["a", "b"]]
  );
});

test("a shared booking groups", () => {
  assert.deepEqual(
    folders([email("a", { booking: "BK-9" }), email("b", { booking: "BK-9" })]),
    [["a", "b"]]
  );
});

test("a shared B/L number groups", () => {
  // The edge the Python copy never had. A carrier replying about a document
  // quotes the B/L and nothing else.
  assert.deepEqual(
    folders([email("a", { bl: "MEDUX1" }), email("b", { bl: "MEDUX1" })]),
    [["a", "b"]]
  );
});

test("different references stay apart", () => {
  assert.deepEqual(
    folders([email("a", { oc: "OC-1" }), email("b", { oc: "OC-2" })]),
    [["a"], ["b"]]
  );
});

test("references are namespaced against email ids", () => {
  // A booking that reads like an email id must not collide with one.
  assert.deepEqual(folders([email("a", { oc: "b" }), email("b")]), [
    ["a"],
    ["b"],
  ]);
});

test("whitespace around a reference does not split a file", () => {
  assert.deepEqual(
    folders([email("a", { oc: " OC-1 " }), email("b", { oc: "OC-1" })]),
    [["a", "b"]]
  );
});

// ----------------------------------------------------------------- bridging

test("an email carrying both joins two references", () => {
  const got = folders([
    email("a", { oc: "OC-1" }), //               names only the OC
    email("b", { oc: "OC-1", booking: "BK-9" }), // the bridge
    email("c", { booking: "BK-9" }), //          names only the booking
  ]);
  assert.deepEqual(got, [["a", "b", "c"]], "a and c connect only through b");
});

test("without the bridge they are separate", () => {
  assert.deepEqual(
    folders([email("a", { oc: "OC-1" }), email("c", { booking: "BK-9" })]),
    [["a"], ["c"]]
  );
});

test("a chain of bridges forms one file", () => {
  const got = folders([
    email("a", { oc: "OC-1" }),
    email("b", { oc: "OC-1", booking: "BK-1" }),
    email("c", { oc: "OC-2", booking: "BK-1" }),
    email("d", { oc: "OC-2" }),
  ]);
  assert.deepEqual(got, [["a", "b", "c", "d"]]);
});

test("a B/L number bridges to a booking", () => {
  const got = folders([
    email("a", { booking: "BK-9" }),
    email("b", { booking: "BK-9", bl: "BL-7" }),
    email("c", { bl: "BL-7" }),
  ]);
  assert.deepEqual(got, [["a", "b", "c"]]);
});

test("order of arrival does not change the components", () => {
  const rows = [
    email("d", { oc: "OC-2" }),
    email("b", { oc: "OC-1", booking: "BK-1" }),
    email("a", { oc: "OC-1" }),
    email("c", { oc: "OC-2", booking: "BK-1" }),
  ];
  assert.deepEqual(folders(rows), [["a", "b", "c", "d"]]);
  assert.deepEqual(folders([...rows].reverse()), [["a", "b", "c", "d"]]);
});

// --------------------------------------------------- resemblance is no edge

test("same customer and lane do not group", () => {
  // email_468 and email_502: both Roxcel to Ashdod, one 40'HC, and different
  // shipments. Only the references decide.
  const alike = {
    bl_number: null,
    consignee: "ROXCEL TRADING GMBH",
    port_of_discharge: "ASHDOD, ISRAEL (ILASH)",
    container_count: "1 X 40'HC",
  };
  const a: GraphRow = { ...email("email_468", { oc: "5ALT-45057" }), shipment: alike };
  const b: GraphRow = { ...email("email_502", { oc: "5RSG-63369" }), shipment: alike };
  assert.deepEqual(folders([a, b]), [["email_468"], ["email_502"]]);
});

// ----------------------------------------------------------------- naming

test("a file is named by its reference, and by its email when it has none", () => {
  assert.equal(shipmentKey(email("e1", { oc: "OC-1", booking: "BK-9" })), "OC-1");
  assert.equal(shipmentKey(email("e1", { booking: "BK-9" })), "BK-9");
  assert.equal(shipmentKey(email("e1", { bl: "BL-7" })), "BL-7");
  assert.equal(shipmentKey(email("e1")), "e1");
  assert.equal(referenceOf(email("e1")), null);
  assert.deepEqual(referencesOf(email("e1", { oc: "A", booking: "B", bl: "C" })), [
    "A",
    "B",
    "C",
  ]);
});

test("a file is named by the reference a desk would quote, not by arrival", () => {
  // The demo thread opens with a booking confirmation carrying no OC number,
  // and the other eleven emails all quote 7QTX-40118.
  const thread = [
    email("e1", { booking: "MEDUTH550281" }),
    email("e2", { oc: "7QTX-40118", booking: "MEDUTH550281" }),
    email("e3", { oc: "7QTX-40118" }),
  ];
  assert.equal(fileKey(thread), "7QTX-40118");
  assert.equal(foldFolder(thread.map((e) => ({ ...e, status: "OK" as Status, severity: null }))).key, "7QTX-40118");
});

test("a file with no OC anywhere falls back to the booking, then the B/L", () => {
  assert.equal(fileKey([email("e1"), email("e2", { booking: "BK-1" })]), "BK-1");
  assert.equal(fileKey([email("e1"), email("e2", { bl: "BL-7" })]), "BL-7");
  assert.equal(fileKey([email("e1"), email("e2")]), "e1");
});

// -------------------------------------------------------------- the verdict

test("a file with no document check in it carries no verdict", () => {
  const f = foldFolder([
    other("e1", "GENERAL", { oc: "OC-1" }),
    other("e2", "INVOICE_QUERY", { oc: "OC-1" }),
  ]);
  assert.equal(f.checked, false);
  assert.equal(f.status, null);
  assert.equal(f.decisive, null);
  assert.equal(f.resolved, false);
});

test("mail that was never checked cannot decide a file", () => {
  // The arrival notice arrives last and is stored as OK. It must not be
  // allowed to clear a draft that is still wrong.
  const f = foldFolder([
    check("e1", "MISMATCH", { oc: "OC-1" }),
    other("e2", "GENERAL", { oc: "OC-1" }),
  ]);
  assert.equal(f.status, "MISMATCH");
  assert.equal(f.decisive?.email_id, "e1");
  assert.equal(f.resolved, false);
});

test("the latest check decides, not the worst one", () => {
  const f = foldFolder([
    check("e1", "MISMATCH", { oc: "OC-1" }),
    check("e2", "OK", { oc: "OC-1" }),
  ]);
  assert.equal(f.status, "OK");
  assert.equal(f.decisive?.email_id, "e2");
});

test("a shipment that was wrong and is now right reads as corrected", () => {
  // The regression this file was written for. Filtering clean checks out
  // before choosing the decisive one made `resolved` unreachable: a folder
  // could only ever end on a failure.
  const f = foldFolder([
    check("e1", "MISMATCH", { oc: "OC-1" }),
    check("e2", "MISMATCH", { oc: "OC-1" }, "serious"),
    check("e3", "OK", { oc: "OC-1" }),
  ]);
  assert.equal(f.status, "OK");
  assert.equal(f.resolved, true);
  assert.equal(f.decisive?.email_id, "e3");
});

test("a file that never failed is not 'corrected'", () => {
  const f = foldFolder([check("e1", "OK", { oc: "OC-1" })]);
  assert.equal(f.resolved, false);
  assert.equal(f.status, "OK");
});

test("a correction that does not land leaves the file failing", () => {
  const f = foldFolder([
    check("e1", "MISMATCH", { oc: "OC-1" }),
    check("e2", "MISMATCH", { oc: "OC-1" }, "serious"),
  ]);
  assert.equal(f.status, "MISMATCH");
  assert.equal(f.severity, "serious");
  assert.equal(f.resolved, false);
});

test("an escalation after a failure is the state of the file", () => {
  const f = foldFolder([
    check("e1", "MISMATCH", { oc: "OC-1" }),
    check("e2", "NEEDS_REVIEW", { oc: "OC-1" }),
  ]);
  assert.equal(f.status, "NEEDS_REVIEW");
  assert.equal(f.resolved, false);
});

test("the fold does not depend on the order rows arrive in", () => {
  const rows = [
    check("e3", "OK", { oc: "OC-1" }),
    check("e1", "MISMATCH", { oc: "OC-1" }),
    check("e2", "MISMATCH", { oc: "OC-1" }, "serious"),
  ];
  const f = foldFolder(rows);
  assert.equal(f.status, "OK");
  assert.equal(f.resolved, true);
  assert.deepEqual(
    f.emails.map((e) => e.email_id),
    ["e1", "e2", "e3"]
  );
});

test("decisiveEmail agrees with the fold", () => {
  const rows = [
    check("e1", "MISMATCH", { oc: "OC-1" }),
    check("e2", "OK", { oc: "OC-1" }),
    other("e3", "GENERAL", { oc: "OC-1" }),
  ];
  assert.equal(decisiveEmail(rows)?.email_id, foldFolder(rows).decisive?.email_id);
});

test("a row loaded without a category is treated as a check", () => {
  // Rows fetched before `category` was carried into list queries. Reading
  // them as non-comparisons would silently empty every queue.
  const legacy: FoldRow = {
    email_id: "e1",
    oc_number: "OC-1",
    booking_ref: null,
    status: "MISMATCH",
    severity: "critical",
  };
  assert.equal(isComparison(legacy), true);
  assert.equal(foldFolder([legacy]).status, "MISMATCH");
});

// ------------------------------------------------------------------ the list

test("files are listed worst first, unchecked mail last", () => {
  const rows: FoldRow[] = [
    other("e5", "SI_REQUEST", { oc: "OC-5" }),
    check("e4", "OK", { oc: "OC-4" }),
    check("e3", "NEEDS_REVIEW", { oc: "OC-3" }),
    check("e2", "MISMATCH", { oc: "OC-2" }),
  ];
  assert.deepEqual(
    groupRows(rows).map((f) => f.key),
    ["OC-2", "OC-3", "OC-4", "OC-5"]
  );
  assert.deepEqual(
    groupRows(rows).map((f) => f.status),
    ["MISMATCH", "NEEDS_REVIEW", "OK", null]
  );
});

test("a thread is one row in the list, not four", () => {
  const rows: FoldRow[] = [
    check("e1", "MISMATCH", { oc: "OC-1" }),
    other("e2", "GENERAL", { oc: "OC-1", booking: "BK-1" }),
    check("e3", "OK", { booking: "BK-1" }),
  ];
  const files = groupRows(rows);
  assert.equal(files.length, 1);
  assert.equal(files[0].emails.length, 3);
  assert.equal(files[0].status, "OK");
  assert.equal(files[0].resolved, true);
});
