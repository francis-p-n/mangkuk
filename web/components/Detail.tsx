"use client";

import { useState } from "react";
import type { Result, Comparison } from "@/lib/format";
import type { Labels } from "@/lib/supabase";
import { who, cargo } from "@/lib/format";
import StatusIcon from "./StatusIcon";
import EmailPanel from "./EmailPanel";
import { Check as CheckIcon, Copy, Mail, TriangleAlert, X } from "lucide-react";

/**
 * The draft the clerk sends to the carrier.
 *
 * It asks rather than instructs, and the distinction is not politeness. What
 * the checker compared was the shipping instruction *on our file*. A
 * disagreement usually means the carrier mistyped something, but it can also
 * mean the instruction was amended after we filed it and the draft is right -
 * and a desk that opens by declaring itself the correct reference has to
 * climb back down in front of a customer when that happens.
 *
 * So it names both readings, asks which is right, and offers the amendment
 * route explicitly. It costs two sentences and it cannot be wrong.
 *
 * Written for a person to read, edit and send from their own mailbox -
 * nothing here sends anything, which is the whole posture of the product.
 */
export function emailText(s: Result, labels: Labels): string {
  const names = labels.field ?? {};
  const ref = s.oc_number || s.booking_ref || "this shipment";
  const one = s.defect_fields.length === 1;
  const lines = s.defect_fields
    .map((f) => {
      const c = s.comparisons.find((x) => x.field === f);
      return (
        `${names[f] ?? f}\n` +
        `  - the shipping instruction on our file says ${c?.si_value}\n` +
        `  - the draft B/L says ${c?.bl_value}`
      );
    })
    .join("\n\n");

  return `Subject: Draft B/L for checking - ${ref}

Dear Sir or Madam,

Thank you for the draft bill of lading for ${ref}.

We have checked it against the shipping instruction on our file, and ${
    one ? "one detail appears" : `${s.defect_fields.length} details appear`
  } to differ:

${lines}

Could you confirm which is correct? If the instruction has been amended since we sent it, please point us to the amendment and we will update our copy. Otherwise, please amend the draft and send it back for confirmation.

Thank you for your help.

Best regards,`;
}

function Row({ c, labels }: { c: Comparison; labels: Labels }) {
  const bad = c.agree === false;
  const unknown = c.agree === null;
  // Shape, colour and words for each of the three outcomes. A comparison
  // table read at speed is exactly where a second channel earns its place.
  const mark = bad ? (
    <span className="mark-bad">
      <X size={13} strokeWidth={2.5} aria-hidden="true" />
      Does not match
    </span>
  ) : unknown ? (
    <span className="dash">
      <TriangleAlert size={13} strokeWidth={2.25} aria-hidden="true" />
      Could not read
    </span>
  ) : (
    <span className="yes">
      <CheckIcon size={13} strokeWidth={2.5} aria-hidden="true" />
      Matches
    </span>
  );

  return (
    <tr className={bad ? "bad" : ""}>
      <th scope="row">{labels.field?.[c.field] ?? c.field}</th>
      <td>
        {c.si_value || "—"}
        <span className="src">{c.si_label || "not on the document"}</span>
      </td>
      <td>
        {c.bl_value || "—"}
        <span className="src">{c.bl_label || "not on the document"}</span>
      </td>
      <td className="verdict-cell">{mark}</td>
    </tr>
  );
}

export default function Detail({ s, labels }: { s: Result; labels: Labels }) {
  const [draft, setDraft] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  const tone = labels.tone?.[s.status] ?? "fine";
  const n = s.defect_fields.length;
  const verdict =
    s.status === "MISMATCH"
      ? `${n === 1 ? "One detail" : n === 2 ? "Two details" : `${n} details`} on the carrier's draft ${
          n === 1 ? "does" : "do"
        } not match your instruction.`
      : s.status === "OK"
        ? "Every detail on the carrier's draft matches your instruction."
        : "We could not check this one, so it needs your eyes.";

  const bad = (s.comparisons ?? []).filter((c) => c.agree === false);
  const sh = s.shipment ?? {};

  async function copy() {
    try {
      await navigator.clipboard.writeText(emailText(s, labels));
      setCopied("Copied");
    } catch {
      setCopied("Could not copy");
    }
    setTimeout(() => setCopied(null), 1800);
  }

  return (
    <div className="detail">
      <h2 id="shipment-name">{who(s)}</h2>
      <p className="sub">
        {s.oc_number ? `Shipment ${s.oc_number}` : "No shipment reference"}
        {s.booking_ref ? ` · booking ${s.booking_ref}` : ""}
      </p>

      <p className="verdict">
        <span className={`tag ${tone}`}>
          <StatusIcon status={s.status} size={13} />
          {labels.status?.[s.status] ?? s.status}
        </span>
        <span>{verdict}</span>
      </p>

      {s.severity && (
        <p className={`band-why ${s.severity}`}>
          <b>{labels.band?.[s.severity] ?? s.severity}</b>
          <span>
            The{" "}
            {(
              labels.field?.[s.severity_field ?? ""] ??
              s.severity_field ??
              ""
            ).toLowerCase()}{" "}
            is the worst of them: {s.severity_reason}.
          </span>
        </p>
      )}

      {cargo(sh) ? <p className="cargo">{cargo(sh)}</p> : <div style={{ height: 14 }} />}

      {s.status === "NEEDS_REVIEW" && (
        <div className="callout">
          {(s.review_reason && labels.reason?.[s.review_reason]) ??
            s.review_reason}
          , so nothing was guessed. Open the documents yourself and check.
        </div>
      )}

      <h3 id="checked-heading">What we checked</h3>
      {s.comparisons?.length ? (
        <>
          <div
            className="table-scroll"
            role="region"
            tabIndex={0}
            aria-labelledby="checked-heading"
          >
            <table aria-describedby="checked-heading">
              <caption className="sr-only">
                Seven details compared between your shipping instruction and
                the carrier&apos;s draft bill of lading
              </caption>
              <thead>
                <tr>
                  <th scope="col">Detail</th>
                  <th scope="col">Your instruction says</th>
                  <th scope="col">The carrier&apos;s draft says</th>
                  <th scope="col">Result</th>
                </tr>
              </thead>
              <tbody>
                {s.comparisons.map((c) => (
                  <Row key={c.field} c={c} labels={labels} />
                ))}
              </tbody>
            </table>
          </div>
          {n > 0 && (
            <p className="todo">
              Ask the carrier to correct{" "}
              {n === 1 ? "this detail" : "these details"} and send a new draft.
            </p>
          )}
        </>
      ) : (
        <p className="nothing">None of the seven details could be compared.</p>
      )}

      {bad.length > 0 && (
        <>
          <h3>Where this came from</h3>
          <details>
            <summary>Show the exact wording on both documents</summary>
            <div className="quote">
              {bad.map((c) => (
                <div key={c.field}>
                  <p>
                    <span className="doc">
                      {labels.field?.[c.field] ?? c.field}, as written on your
                      instruction (line {c.si_line}):
                    </span>
                    <span className="line">
                      {c.si_label}: {c.si_value}
                    </span>
                  </p>
                  <p>
                    <span className="doc">
                      and on the carrier&apos;s draft (line {c.bl_line}):
                    </span>
                    <span className="line">
                      {c.bl_label}: {c.bl_value}
                    </span>
                  </p>
                </div>
              ))}
            </div>
          </details>
        </>
      )}

      {s.status === "MISMATCH" && (
        <>
          <div className="buttons">
            <button
              type="button"
              className="btn go"
              onClick={() => setDraft(true)}
            >
              <Mail size={15} strokeWidth={2.25} aria-hidden="true" />
              {draft ? "Rewrite the email" : "Write the email to the carrier"}
            </button>
            <button type="button" className="btn" onClick={copy}>
              {copied ? (
                <CheckIcon size={15} strokeWidth={2.5} aria-hidden="true" />
              ) : (
                <Copy size={15} strokeWidth={2.25} aria-hidden="true" />
              )}
              {copied ?? "Copy the details"}
            </button>
          </div>
          {draft && (
            <div aria-live="polite">
              <div className="email">
                <div className="h">Ready to send from your own mailbox</div>
                <pre>{emailText(s, labels)}</pre>
              </div>
              <p className="after">
                Read it over, change anything you want, then send it yourself.
              </p>
            </div>
          )}
        </>
      )}

      <EmailPanel s={s} />
    </div>
  );
}
