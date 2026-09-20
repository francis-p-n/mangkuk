// Corrections the person at the desk has made to the comparator.
//
// A clerk disagreeing with a verdict is the most informative thing that
// happens to this system, and normally it is said out loud and lost. This
// keeps it, in exactly the shape sdoc/learned.py reads, so the download can
// be dropped straight into the repo and become a permanent rule and a test.
//
// Nothing here changes a verdict on screen by itself. The record is the
// point; applying it is a deliberate step someone takes with the report in
// front of them, because silencing a check should never be a side effect of
// clicking once.
window.SDOC = window.SDOC || {};
window.SDOC.learned = (function () {
  "use strict";

  const KEY = "sdoc-learned";
  const SCHEMA = 1;

  // Browser storage can throw outright in a private window or with site data
  // blocked, so every read and write survives failing.
  function all() {
    try {
      const raw = localStorage.getItem(KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) { return []; }
  }

  function save(list) {
    try { localStorage.setItem(KEY, JSON.stringify(list)); return true; }
    catch (e) { return false; }
  }

  // One pair of values, in either order: which document happened to hold
  // which value is an accident of who typed what.
  function same(a, b) {
    return String(a || "").trim().toUpperCase() === String(b || "").trim().toUpperCase();
  }

  function match(list, field, si, bl) {
    return list.findIndex(e => e.field === field &&
      ((same(e.si_value, si) && same(e.bl_value, bl)) ||
       (same(e.si_value, bl) && same(e.bl_value, si))));
  }

  function find(field, si, bl) {
    const list = all();
    const at = match(list, field, si, bl);
    return at === -1 ? null : list[at];
  }

  // Re-teaching a pair corrects the earlier answer rather than stacking a
  // second, contradictory one beside it.
  function record({ field, si_value, bl_value, agree, was, note }) {
    const list = all();
    const at = match(list, field, si_value, bl_value);
    const entry = {
      field: field,
      si_value: si_value,
      bl_value: bl_value,
      agree: !!agree,
      was: was === undefined ? null : was,
      who: (window.SDOC.session && window.SDOC.session.user()) || "",
      when: new Date().toISOString().slice(0, 10),
      note: note || "",
    };
    if (at === -1) list.push(entry); else list[at] = entry;
    save(list);
    return entry;
  }

  function forget(field, si, bl) {
    const list = all();
    const at = match(list, field, si, bl);
    if (at === -1) return false;
    list.splice(at, 1);
    return save(list);
  }

  function clear() { save([]); }

  function payload() {
    return { schema: SCHEMA, overrides: all() };
  }

  // Handed to the person as a file, because the next step is a command they
  // run against the repo with the blast-radius report in front of them.
  function download() {
    const text = JSON.stringify(payload(), null, 2) + "\n";
    const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "overrides.json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return { all, find, record, forget, clear, payload, download, count: () => all().length };
})();
