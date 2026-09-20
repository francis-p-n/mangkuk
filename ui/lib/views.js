// Shared pieces of screen. The home page and the search page draw the same
// shipment the same way, because there is only one implementation of it.
window.SDOC = window.SDOC || {};
window.SDOC.views = (function () {
  "use strict";
  const F = window.SDOC.fmt;
  const esc = F.esc;

  const data = () => window.SDOC.data || {};
  const V = () => (data().labels || {});
  const NAMES = () => V().field || {};
  const WHY = () => V().reason || {};
  const TAG = () => V().status || {};
  const TONE = () => V().tone || {};
  const BAND = () => V().band || {};
  const BAND_WHY = () => V().band_blurb || {};

  function issue(s) {
    if (s.status === "MISMATCH") {
      const names = s.defect_fields.map(f => (NAMES()[f] || f).toLowerCase());
      const list = names.length === 1 ? names[0]
        : names.slice(0, -1).join(", ") + " and " + names[names.length - 1];
      return `${list.charAt(0).toUpperCase() + list.slice(1)} ${names.length === 1 ? "does" : "do"} not match`;
    }
    if (s.status === "NEEDS_REVIEW") return WHY()[s.review_reason] || s.review_reason;
    return "Everything matches";
  }

  // A row in any list of shipments. `href` makes it a link (home page, where
  // choosing one leaves the page); otherwise it is a button (search page,
  // where the detail opens beside it).
  function row(s, { href, current } = {}) {
    const tone = TONE()[s.status] || "fine";
    // The band replaces the status tag on a mismatch: "Needs fixing" is
    // already obvious from the queue it is sitting in, and how urgently is
    // the thing the reader does not know.
    const badge = s.severity
      ? `<span class="vis-tag band ${esc(s.severity)}">${esc(BAND()[s.severity] || s.severity)}</span>`
      : `<span class="vis-tag ${tone}">${esc(TAG()[s.status] || s.status)}</span>`;
    const inner =
      `<span class="who">${esc(F.who(s))}</span>` +
      `<span class="where">${esc(s.oc_number || s.booking_ref || "no reference")}` +
      `${F.route(s.shipment) ? " · " + esc(F.route(s.shipment)) : ""}</span>` +
      `<span class="issue ${tone}">${badge}${esc(issue(s))}</span>`;
    return href
      ? `<a class="row s-${tone}" href="${esc(href)}">${inner}</a>`
      : `<button type="button" class="row s-${tone}" data-id="${esc(s.email_id)}"` +
        ` aria-current="${current ? "true" : "false"}">${inner}</button>`;
  }

  function comparisonRow(c) {
    const bad = c.agree === false, unknown = c.agree === null;
    const mark = bad
      ? '<span class="mark-bad">Does not match</span>'
      : unknown ? '<span class="dash">Could not read</span>'
                : '<span class="yes">Matches</span>';
    return `<tr class="${bad ? "bad" : ""}">
      <th scope="row">${esc(NAMES()[c.field] || c.field)}</th>
      <td>${esc(c.si_value || "—")}<span class="src">${esc(c.si_label || "not on the document")}</span></td>
      <td>${esc(c.bl_value || "—")}<span class="src">${esc(c.bl_label || "not on the document")}</span></td>
      <td class="verdict-cell">${mark}</td></tr>`;
  }

  function email(s) {
    const ref = s.oc_number || s.booking_ref || "this shipment";
    const lines = s.defect_fields.map(f => {
      const c = s.comparisons.find(x => x.field === f);
      return `${NAMES()[f] || f}\n  - our shipping instruction says ${c.si_value}\n  - your draft B/L says ${c.bl_value}`;
    }).join("\n\n");
    return `Subject: Draft B/L correction needed - ${ref}

Dear Sir or Madam,

Thank you for the draft bill of lading for ${ref}.

We have checked it against our shipping instruction and found the following ${
      s.defect_fields.length === 1 ? "difference" : "differences"}:

${lines}

Our shipping instruction is the correct reference. Please amend the draft and send it back for confirmation.

Thank you for your assistance.

Best regards,`;
  }

  // The full shipment panel, identical wherever it is shown.
  function detail(s) {
    const sh = s.shipment || {}, tone = TONE()[s.status] || "fine";
    const n = s.defect_fields.length;
    const verdict = s.status === "MISMATCH"
      ? `${n === 1 ? "One detail" : n === 2 ? "Two details" : n + " details"} on the carrier's draft ${n === 1 ? "does" : "do"} not match your instruction.`
      : s.status === "OK" ? "Every detail on the carrier's draft matches your instruction."
      : "We could not check this one, so it needs your eyes.";

    const table = (s.comparisons && s.comparisons.length) ? `
      <h3 id="checked-heading">What we checked</h3>
      <div class="table-scroll" role="region" tabindex="0"
           aria-labelledby="checked-heading">
      <table aria-describedby="checked-heading">
        <caption class="sr-only">Seven details compared between your shipping instruction and the carrier's draft bill of lading</caption>
        <thead><tr><th scope="col">Detail</th><th scope="col">Your instruction says</th>
          <th scope="col">The carrier's draft says</th><th scope="col">Result</th></tr></thead>
        <tbody>${s.comparisons.map(comparisonRow).join("")}</tbody></table></div>
      ${n ? `<p class="todo">Ask the carrier to correct ${n === 1 ? "this detail" : "these details"} and send a new draft.</p>` : ""}`
      : `<h3>What we checked</h3><p class="nothing">None of the seven details could be compared.</p>`;

    const bad = (s.comparisons || []).filter(c => c.agree === false);
    const quotes = bad.map(c => `<p><span class="doc">${esc(NAMES()[c.field] || c.field)}, as written on your instruction (line ${c.si_line}):</span>
        <span class="line">${esc(c.si_label)}: ${esc(c.si_value)}</span></p>
      <p><span class="doc">and on the carrier's draft (line ${c.bl_line}):</span>
        <span class="line">${esc(c.bl_label)}: ${esc(c.bl_value)}</span></p>`).join("");

    return `
      <h2 id="shipment-name">${esc(F.who(s))}</h2>
      <p class="sub">${esc(s.oc_number ? "Shipment " + s.oc_number : "No shipment reference")}${
        s.booking_ref ? " · booking " + esc(s.booking_ref) : ""}${
        sh.bl_number ? " · B/L " + esc(sh.bl_number) : ""}</p>

      <p class="verdict"><span class="tag ${tone}">${esc(TAG()[s.status] || s.status)}</span>
        <span>${esc(verdict)}</span></p>
      ${s.severity ? `<p class="band-why ${esc(s.severity)}">
        <b>${esc(BAND()[s.severity] || s.severity)}</b>
        <span>The ${esc((NAMES()[s.severity_field] || s.severity_field).toLowerCase())
          } is the worst of them: ${esc(s.severity_reason)}.</span></p>` : ""}
      ${F.cargo(sh) ? `<p class="cargo">${esc(F.cargo(sh))}</p>` : "<div style='height:14px'></div>"}

      ${s.status === "NEEDS_REVIEW" ? `<div class="callout">${esc(WHY()[s.review_reason] || s.review_reason)}, so nothing was guessed. Open the documents yourself and check.</div>` : ""}

      ${table}

      ${quotes ? `<h3>Where this came from</h3>
        <details><summary>Show the exact wording on both documents</summary>
        <div class="quote">${quotes}</div></details>` : ""}

      ${s.status === "MISMATCH" ? `<div class="buttons">
        <button type="button" class="btn go" data-act="draft">Write the email to the carrier</button>
        <button type="button" class="btn" data-act="copy">Copy the details</button>
      </div><div data-slot="draft" aria-live="polite"></div>` : ""}`;
  }

  // Wire the two buttons the detail panel may contain.
  function bindDetail(root, s) {
    const slot = root.querySelector('[data-slot="draft"]');
    const draft = root.querySelector('[data-act="draft"]');
    if (draft) draft.addEventListener("click", () => {
      slot.innerHTML = `<div class="email"><div class="h">Ready to send from your own mailbox</div>
        <pre>${esc(email(s))}</pre></div>
        <p class="after">Read it over, change anything you want, then send it yourself.</p>`;
      draft.textContent = "Rewrite the email";
    });
    const copy = root.querySelector('[data-act="copy"]');
    if (copy) copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(email(s)); copy.textContent = "Copied"; }
      catch (e) { copy.textContent = "Could not copy"; }
      setTimeout(() => { copy.textContent = "Copy the details"; }, 1800);
    });
  }

  return { issue, row, detail, bindDetail, email, BAND, BAND_WHY };
})();
