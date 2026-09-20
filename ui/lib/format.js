// Turning stored values into the words a shipping clerk uses.
// Pure functions, no DOM, shared by every page.
window.SDOC = window.SDOC || {};
window.SDOC.fmt = (function () {
  "use strict";

  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // Legal forms and codes keep their capitals; "Fz-Llc" reads as a typo.
  const KEEP_CAPS = new Set(["LLC", "FZ", "FZE", "FZCO", "LTD", "PTE", "PTY", "SDN",
    "BHD", "INC", "CO", "SP", "BV", "NV", "AG", "SA", "PT", "UAB", "JSC", "PLC",
    "KPP", "3S", "USA", "UAE"]);
  const FIXES = { Gmbh: "GmbH" };

  const title = s => !s ? "" : String(s).toLowerCase()
    .replace(/\b([a-z])/g, m => m.toUpperCase())
    .split(/(\s|-|\/)/).map(w => {
      if (FIXES[w]) return FIXES[w];
      // Brackets and stops travel with the token: "(Llc)", "Ltd.".
      const core = w.replace(/[^A-Za-z]/g, "");
      return core && KEEP_CAPS.has(core.toUpperCase())
        ? w.replace(core, core.toUpperCase()) : w;
    }).join("");

  // City only: drop the UN/LOCODE, keep a terminal name like (Westport).
  const cityOf = p => title(String(p || "").replace(/\s*\([A-Z]{5}\)/g, "").split(",")[0].trim());

  // Cut on a word boundary; a heading ending "PAPERONE DIGITA" looks broken.
  function clip(text, max) {
    const s = String(text || "").replace(/\s*_\s*/g, " · ").replace(/\s+/g, " ").trim();
    if (s.length <= max) return s;
    const cut = s.slice(0, max);
    const space = cut.lastIndexOf(" ");
    return (space > max * 0.55 ? cut.slice(0, space) : cut).replace(/[\s·,.-]+$/, "") + "…";
  }

  const BOX = { HC: "ft high-cube", GP: "ft standard", DV: "ft standard", DC: "ft standard",
                RF: "ft reefer", FCL: "ft", OT: "ft open-top", FR: "ft flat-rack" };

  // "6 x 40'HC" is a code. "6 forty-foot high-cube containers" is the job.
  function boxes(spec) {
    const m = /(\d+)\s*[xX]\s*(\d+)\s*'?\s*([A-Za-z]+)?/.exec(spec || "");
    if (!m) return spec || "";
    const kind = BOX[(m[3] || "").toUpperCase()] || "ft";
    return `${m[1]} × ${m[2]}${kind} container${m[1] === "1" ? "" : "s"}`;
  }
  const weight = w => String(w || "").replace(/\s*KGS?\b/i, " kg").trim();

  // Named by the customer when known, by the email when not.
  const who = s => title(s.shipment.consignee) || clip(s.subject, 52) || s.email_id;

  function route(sh, joiner) {
    return [sh.loading_port || sh.port_of_loading, sh.discharge_port || sh.port_of_discharge]
      .filter(Boolean).map(cityOf).join(joiner || " to ");
  }

  // One sentence about the cargo, instead of a grid of codes.
  function cargo(sh) {
    const bits = [];
    if (sh.container_count) {
      let c = boxes(sh.container_count);
      if (sh.gross_weight_kg) c += `, ${weight(sh.gross_weight_kg)}`;
      if (sh.commodity) c += ` of ${title(sh.commodity)}`;
      bits.push(c + ".");
    } else if (sh.commodity) bits.push(title(sh.commodity) + ".");
    const from = cityOf(sh.loading_port || sh.port_of_loading);
    const to = cityOf(sh.discharge_port || sh.port_of_discharge);
    if (from && to) bits.push(`Sailing from ${from} to ${to}${sh.vessel ? " on " + sh.vessel : ""}.`);
    else if (sh.vessel) bits.push(`On ${sh.vessel}.`);
    return bits.join(" ");
  }

  return { esc, title, cityOf, clip, boxes, weight, who, route, cargo };
})();
