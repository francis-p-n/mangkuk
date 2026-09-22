// Turning stored values into the words a shipping clerk uses.
//
// A direct port of ui/lib/format.js. The rules here are domain judgements
// that took the desk cases to get right - "Fz-Llc" reads as a typo, a
// heading ending "PAPERONE DIGITA" looks broken - so they are carried over
// rather than reinvented, and eval/desk_cases.py still governs them.
//
// Pure functions, no React, no DOM. Escaping is React's job here, so the
// `esc` of the original is gone.

export type Shipment = {
  shipper?: string | null;
  consignee?: string | null;
  notify_party?: string | null;
  port_of_loading?: string | null;
  port_of_discharge?: string | null;
  loading_port?: string | null;
  discharge_port?: string | null;
  container_count?: string | null;
  gross_weight_kg?: string | null;
  vessel?: string | null;
  voyage?: string | null;
  commodity?: string | null;
  booking?: string | null;
  oc_number?: string | null;
  /** Printed on the draft, and a third name for the same shipment. */
  bl_number?: string | null;
};

export type Comparison = {
  field: string;
  si_value: string | null;
  bl_value: string | null;
  agree: boolean | null;
  si_label: string | null;
  bl_label: string | null;
  si_line: number | null;
  bl_line: number | null;
  taught: boolean;
};

export type DocumentRef = {
  role: string;
  present: boolean;
  path: string | null;
  format: string | null;
  readable: boolean;
  doc_type: string | null;
  type_matches_role: boolean;
  error: string | null;
};

export type Result = {
  email_id: string;
  category: string;
  rule: string | null;
  status: "OK" | "MISMATCH" | "NEEDS_REVIEW";
  review_reason: string | null;
  has_defect: boolean;
  defect_fields: string[];
  subject: string | null;
  sender: string | null;
  body: string | null;
  oc_number: string | null;
  booking_ref: string | null;
  note: string | null;
  severity: string | null;
  severity_field: string | null;
  severity_reason: string | null;
  documents: DocumentRef[];
  comparisons: Comparison[];
  shipment: Shipment;
};

// Legal forms and codes keep their capitals; "Fz-Llc" reads as a typo.
const KEEP_CAPS = new Set([
  "LLC", "FZ", "FZE", "FZCO", "LTD", "PTE", "PTY", "SDN", "BHD", "INC", "CO",
  "SP", "BV", "NV", "AG", "SA", "PT", "UAB", "JSC", "PLC", "KPP", "3S", "USA",
  "UAE",
]);
const FIXES: Record<string, string> = { Gmbh: "GmbH" };

function title(s: string | null | undefined): string {
  if (!s) return "";
  return String(s)
    .toLowerCase()
    .replace(/\b([a-z])/g, (m) => m.toUpperCase())
    .split(/(\s|-|\/)/)
    .map((w) => {
      if (FIXES[w]) return FIXES[w];
      // Brackets and stops travel with the token: "(Llc)", "Ltd.".
      const core = w.replace(/[^A-Za-z]/g, "");
      return core && KEEP_CAPS.has(core.toUpperCase())
        ? w.replace(core, core.toUpperCase())
        : w;
    })
    .join("");
}

// City only: drop the UN/LOCODE, keep a terminal name like (Westport).
const cityOf = (p: string | null | undefined): string =>
  title(
    String(p || "")
      .replace(/\s*\([A-Z]{5}\)/g, "")
      .split(",")[0]
      .trim()
  );

// Cut on a word boundary; a heading ending "PAPERONE DIGITA" looks broken.
function clip(text: string | null | undefined, max: number): string {
  const s = String(text || "")
    .replace(/\s*_\s*/g, " · ")
    .replace(/\s+/g, " ")
    .trim();
  if (s.length <= max) return s;
  const cut = s.slice(0, max);
  const space = cut.lastIndexOf(" ");
  return (
    (space > max * 0.55 ? cut.slice(0, space) : cut).replace(/[\s·,.-]+$/, "") +
    "…"
  );
}

const BOX: Record<string, string> = {
  HC: "ft high-cube", GP: "ft standard", DV: "ft standard", DC: "ft standard",
  RF: "ft reefer", FCL: "ft", OT: "ft open-top", FR: "ft flat-rack",
};

// "6 x 40'HC" is a code. "6 forty-foot high-cube containers" is the job.
function boxes(spec: string | null | undefined): string {
  const m = /(\d+)\s*[xX]\s*(\d+)\s*'?\s*([A-Za-z]+)?/.exec(spec || "");
  if (!m) return spec || "";
  const kind = BOX[(m[3] || "").toUpperCase()] || "ft";
  return `${m[1]} × ${m[2]}${kind} container${m[1] === "1" ? "" : "s"}`;
}

const weight = (w: string | null | undefined): string =>
  String(w || "").replace(/\s*KGS?\b/i, " kg").trim();

// Named by the customer when known, by the email when not.
//
// Typed by what it reads rather than by Result, so a list row carrying none
// of the heavy JSONB can still be named without being widened back out to a
// full record just to satisfy a signature.
export type Named = {
  email_id: string;
  subject: string | null;
  shipment: Shipment;
};

// A shipment with no readable consignee is named by its email instead, and
// a reply marker is not part of that name: "RE · AFRT - LONG BEACH · US…"
// spends its first characters saying nothing and pushes the useful part off
// the end of the line.
const REPLY_MARKER = /^\s*(?:(?:re|fw|fwd)(?![a-z0-9])[\s_:.·-]*)+/i;

export const who = (s: Named): string =>
  title(s.shipment?.consignee) ||
  clip(String(s.subject ?? "").replace(REPLY_MARKER, ""), 52) ||
  s.email_id;

export function route(sh: Shipment | null | undefined, joiner = " to "): string {
  if (!sh) return "";
  return [
    sh.loading_port || sh.port_of_loading,
    sh.discharge_port || sh.port_of_discharge,
  ]
    .filter(Boolean)
    .map((p) => cityOf(p as string))
    .join(joiner);
}

// One sentence about the cargo, instead of a grid of codes.
export function cargo(sh: Shipment | null | undefined): string {
  if (!sh) return "";
  const bits: string[] = [];
  if (sh.container_count) {
    let c = boxes(sh.container_count);
    if (sh.gross_weight_kg) c += `, ${weight(sh.gross_weight_kg)}`;
    if (sh.commodity) c += ` of ${title(sh.commodity)}`;
    bits.push(c + ".");
  } else if (sh.commodity) {
    bits.push(title(sh.commodity) + ".");
  }
  const from = cityOf(sh.loading_port || sh.port_of_loading);
  const to = cityOf(sh.discharge_port || sh.port_of_discharge);
  if (from && to) {
    bits.push(
      `Sailing from ${from} to ${to}${sh.vessel ? " on " + sh.vessel : ""}.`
    );
  } else if (sh.vessel) {
    bits.push(`On ${sh.vessel}.`);
  }
  return bits.join(" ");
}
