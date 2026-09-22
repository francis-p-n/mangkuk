/**
 * The words a row puts on screen.
 *
 *     npm test --prefix web
 *
 * These are small, and they are here because the name at the top of a row is
 * the first thing anyone reads. A shipment whose documents could not be
 * parsed has no consignee, so it is named by its email subject instead - and
 * a regex that eats one character too many turns "REQUEST SI" into
 * "QUEST SI" on twenty rows without anything failing.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { who, route, cargo } from "./format.ts";
import type { Shipment } from "./format.ts";

const named = (consignee: string | null, subject: string | null) => ({
  email_id: "email_001",
  subject,
  shipment: { consignee } as Shipment,
});

test("a shipment is named by its customer", () => {
  assert.equal(who(named("LINDEN & HALE PAPER LIMITED", "anything")),
               "Linden & Hale Paper Limited");
});

test("legal forms and codes keep their capitals", () => {
  assert.equal(who(named("EASTLIGHT PAPER CO (LLC)", null)),
               "Eastlight Paper CO (LLC)");
  assert.equal(who(named("ROXCEL TRADING GMBH", null)),
               "Roxcel Trading GmbH");
});

test("with no readable consignee it is named by the email", () => {
  assert.equal(who(named(null, "AFRT - LONG BEACH")), "AFRT - LONG BEACH");
});

test("a reply marker is not part of the name", () => {
  assert.equal(who(named(null, "RE_ AFRT - LONG BEACH")), "AFRT - LONG BEACH");
  assert.equal(who(named(null, "FW: AFRT - LONG BEACH")), "AFRT - LONG BEACH");
  assert.equal(who(named(null, "RE: FW: AFRT")), "AFRT");
});

test("a word that merely starts with 're' is left alone", () => {
  // The bug this file exists for: without a word boundary, "REQUEST SI"
  // renders as "QUEST SI" - and it is 132 rows of the corpus.
  assert.equal(who(named(null, "REQUEST SI _ GDANSK")), "REQUEST SI · GDANSK");
  assert.equal(who(named(null, "Reminder_Paper - Submit SI")),
               "Reminder · Paper - Submit SI");
});

test("an email with nothing to name it falls back to its id", () => {
  assert.equal(who(named(null, null)), "email_001");
  assert.equal(who(named(null, "RE:")), "email_001");
});

test("a long subject is cut on a word boundary", () => {
  const name = who(named(null, "TO CONFIRM DOCS AND EVERYTHING ELSE ABOUT " +
                               "THIS PARTICULAR SHIPMENT TODAY"));
  assert.ok(name.length <= 53, name);
  assert.ok(name.endsWith("…"), name);
  assert.ok(!name.includes("PARTICU "), "cut mid-word");
});

test("a route reads as cities, without the locode", () => {
  assert.equal(
    route({ port_of_loading: "SINGAPORE (SGSIN)",
            port_of_discharge: "KARACHI, PAKISTAN (PKKHI)" }),
    "Singapore to Karachi"
  );
});

test("a route with only one end does not say 'to'", () => {
  assert.equal(route({ port_of_loading: "SINGAPORE (SGSIN)" }), "Singapore");
  assert.equal(route(null), "");
});

test("cargo reads as a sentence, not a grid of codes", () => {
  assert.equal(
    cargo({ container_count: "6 x 40'HC", gross_weight_kg: "131,058 KG",
            commodity: "COATED IVORY BOARD" }),
    "6 × 40ft high-cube containers, 131,058 kg of Coated Ivory Board."
  );
});

test("one container is not 'containers'", () => {
  assert.ok(cargo({ container_count: "1 x 20'GP" })
    .startsWith("1 × 20ft standard container."));
});
