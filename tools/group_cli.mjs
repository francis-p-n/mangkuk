/**
 * The shipment graph, on the command line.
 *
 *     node tools/group_cli.mjs < rows.json
 *
 * Reads a JSON array of result rows on stdin and writes the files they group
 * into on stdout. Exists so the Python suite can assert against the grouping
 * that actually ships rather than against a second copy of the algorithm: the
 * copy `tests/test_grouping.py` used to carry had already drifted, and the
 * real `componentsOf` could be broken without a single test noticing.
 *
 * Node reads TypeScript directly (type stripping, v22.6+), so this imports
 * web/lib/graph.ts with no build step. That file imports nothing, which is
 * what makes it reachable from here.
 */
import { groupRows } from "../web/lib/graph.ts";

const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
const rows = JSON.parse(Buffer.concat(chunks).toString("utf8") || "[]");

const files = groupRows(rows).map((f) => ({
  key: f.key,
  reference: f.reference,
  emails: f.emails.map((e) => e.email_id),
  checked: f.checked,
  status: f.status,
  severity: f.severity,
  decisive: f.decisive ? f.decisive.email_id : null,
  resolved: f.resolved,
}));

process.stdout.write(JSON.stringify({ files }, null, 1));
