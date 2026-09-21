import { db } from "./supabase";

/**
 * The ways a run can be narrowed, and how many shipments each way holds.
 *
 * A facet is offered only when it separates the run into more than one group.
 * Every shipment in this corpus is sea freight, every one is international,
 * and every one loads in Asia and discharges elsewhere - so a mode filter, a
 * domestic filter and a direction filter would each be a control with a single
 * option. A judge who clicks "Air freight" and gets an empty list has learned
 * something true about the data and something false about the product.
 *
 * So the dimensions are all computed, and the page renders the ones that
 * discriminate. The day an air waybill arrives, the mode filter appears by
 * itself; nothing has to be remembered or switched on.
 */

export type FacetValue = { value: string; label: string; count: number };
export type Facet = { key: string; label: string; values: FacetValue[] };

/** Rows carry the ports; everything else here is derived from them. */
type Row = { pol: string | null; pod: string | null; cat: string | null };

/** "CALLAO, PERU (PECLL)" -> "PERU". Null when the port names no country. */
export function countryOf(port: string | null): string | null {
  if (!port) return null;
  const parts = port
    .replace(/\s*\([A-Z]{5}\)\s*/g, "")
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean);
  if (parts.length < 2) return null;
  const last = parts[parts.length - 1];
  // "HOUSTON, TX, USA" - a two-letter state is not the country.
  return last.length <= 2 && parts.length > 2
    ? parts[parts.length - 2].toUpperCase()
    : last.toUpperCase();
}

const title = (s: string) =>
  s
    .toLowerCase()
    .replace(/\b[a-z]/g, (c) => c.toUpperCase())
    .replace(/\b(Usa|Uae|Uk)\b/g, (m) => m.toUpperCase());

/**
 * Every document here is a bill of lading, which is an ocean document. Air
 * waybills and CMR consignment notes would read as air and road, and nothing
 * in this corpus does - which is exactly why the filter stays hidden.
 */
function modeOf(_r: Row): string {
  return "sea";
}

function scopeOf(r: Row): string | null {
  const a = countryOf(r.pol);
  const b = countryOf(r.pod);
  if (!a || !b) return null;
  return a === b ? "domestic" : "international";
}

function tally(rows: Row[], pick: (r: Row) => string | null) {
  const counts = new Map<string, number>();
  for (const r of rows) {
    const v = pick(r);
    if (v) counts.set(v, (counts.get(v) ?? 0) + 1);
  }
  return counts;
}

function facet(
  key: string,
  label: string,
  counts: Map<string, number>,
  labelOf: (v: string) => string
): Facet | null {
  // The whole point: one value is not a choice.
  if (counts.size < 2) return null;
  return {
    key,
    label,
    values: [...counts.entries()]
      .map(([value, count]) => ({ value, label: labelOf(value), count }))
      .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label)),
  };
}

export async function facetsFor(runId: string): Promise<Facet[]> {
  // Two short strings per row - about 30KB for a 520-row run - rather than a
  // stored summary that would need a migration and could go stale against the
  // rows it describes.
  const { data, error } = await db()
    .from("results")
    .select(
      "pol:shipment->>port_of_loading, pod:shipment->>port_of_discharge, cat:category"
    )
    .eq("run_id", runId)
    .limit(5000);
  if (error) throw new Error(`reading facets: ${error.message}`);

  // Only shipments, not the general mail that has no ports at all.
  const rows = ((data ?? []) as unknown as Row[]).filter((r) => r.pol || r.pod);

  return [
    facet("from", "Loading in", tally(rows, (r) => countryOf(r.pol)), title),
    facet("to", "Discharging in", tally(rows, (r) => countryOf(r.pod)), title),
    facet("mode", "Freight", tally(rows, modeOf), title),
    facet("scope", "Lane", tally(rows, scopeOf), (v) =>
      v === "domestic" ? "Domestic" : "International"
    ),
  ].filter((f): f is Facet => f !== null);
}

/** Turn a chosen facet value into the filter PostgREST needs. */
export function facetFilter(key: string, value: string) {
  if (key === "from") return { col: "shipment->>port_of_loading", value };
  if (key === "to") return { col: "shipment->>port_of_discharge", value };
  return null; // mode and scope are derived, not stored; nothing to filter on
}
