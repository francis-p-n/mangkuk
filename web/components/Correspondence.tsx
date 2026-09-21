"use client";

import { Mail } from "lucide-react";
import type { Labels } from "@/lib/supabase";
import type { Result } from "@/lib/format";
import { isComparison } from "@/lib/graph";
import { useResult } from "@/lib/useResult";
import StatusIcon from "./StatusIcon";
import Detail from "./Detail";
import PanelSkeleton from "./PanelSkeleton";

/**
 * One shipment's file: every email about it, and the one open beside them.
 *
 * The thread used to be a static list with the deciding check pinned open
 * underneath it, so the other eleven emails were labels you could not read.
 * They are the file - the instruction, the first draft, the correction, the
 * arrival notice - and a clerk reconstructing what happened needs to open
 * them, in place, without losing the thread they are reading.
 */

export type ThreadEmail = {
  email_id: string;
  category: string;
  status: "OK" | "MISMATCH" | "NEEDS_REVIEW";
  subject: string | null;
  sender: string | null;
  severity: string | null;
};

type Props = {
  runId: string;
  emails: ThreadEmail[];
  labels: Labels;
  initial: Result | null;
};

export default function Correspondence({
  runId,
  emails,
  labels,
  initial,
}: Props) {
  const { openId, shown, loading, failed, open } = useResult(runId, initial);

  return (
    <main className="cols" id="results">
      <section className="card" aria-labelledby="thread-heading">
        <h2 className="listtop" id="thread-heading">
          The correspondence
        </h2>
        <ol className="thread">
          {emails.map((e) => {
            const isOpen = e.email_id === openId;
            // A booking confirmation belongs in the file, but it was never
            // compared - so it reports what kind of mail it is rather than a
            // verdict it does not have.
            const checked = isComparison(e);
            const tone = checked ? labels.tone?.[e.status] ?? "fine" : "idle";
            return (
              <li key={e.email_id}>
                <button
                  type="button"
                  className={`thread-item${isOpen ? " is-open" : ""}`}
                  aria-current={isOpen ? "true" : undefined}
                  onClick={() => open(e.email_id)}
                >
                  <Mail size={14} strokeWidth={2} aria-hidden="true" />
                  <span className="thread-body">
                    <span className="thread-subject">
                      {e.subject ?? "(no subject)"}
                    </span>
                    <span className="thread-from">{e.sender}</span>
                    <span className={`thread-state ${tone}`}>
                      <StatusIcon
                        status={checked ? e.status : "UNCHECKED"}
                        size={12}
                      />
                      {checked
                        ? labels.status?.[e.status] ?? e.status
                        : labels.category?.[e.category] ?? "No check"}
                      {isOpen && emails.length > 1 && " — shown here"}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
        {emails.length === 1 && (
          <p className="thread-note">
            Only one email mentions this reference. Anything else the carrier
            sends about it files itself here.
          </p>
        )}
      </section>

      <section
        className="card"
        aria-labelledby="shipment-name"
        aria-live="polite"
        aria-busy={loading}
      >
        {loading ? (
          <PanelSkeleton />
        ) : shown ? (
          <Detail s={shown} labels={labels} />
        ) : (
          <p className="allclear" style={{ padding: "28px 22px" }}>
            {failed ?? "Nothing in this file has been compared."}
          </p>
        )}
      </section>
    </main>
  );
}
