import Link from "next/link";
import type { Result } from "@/lib/format";
import type { ListRow } from "@/lib/supabase";
import type { Labels } from "@/lib/supabase";
import { who, route } from "@/lib/format";
import StatusIcon from "./StatusIcon";

/**
 * What is wrong with this shipment, in a clerk's words.
 *
 * Ported from ui/lib/views.js. The list-joining matters: "Consignee and
 * loading port do not match" reads; "consignee, loading_port" does not.
 */
export function issue(s: ListRow | Result, labels: Labels): string {
  const names = labels.field ?? {};
  if (s.status === "MISMATCH") {
    const parts = s.defect_fields.map((f) =>
      (names[f] ?? f).toLowerCase()
    );
    const list =
      parts.length === 1
        ? parts[0]
        : parts.slice(0, -1).join(", ") + " and " + parts[parts.length - 1];
    return `${list.charAt(0).toUpperCase()}${list.slice(1)} ${
      parts.length === 1 ? "does" : "do"
    } not match`;
  }
  if (s.status === "NEEDS_REVIEW") {
    return (
      (s.review_reason && labels.reason?.[s.review_reason]) ??
      s.review_reason ??
      "Needs a look"
    );
  }
  return "Everything matches";
}

type Props = {
  s: ListRow | Result;
  labels: Labels;
  href?: string;
  current?: boolean;
  /** How many emails are filed under this shipment. */
  count?: number;
  /** It failed once and a later draft came back clean. */
  resolved?: boolean;
};

/**
 * A row in any list of shipments. A link when choosing one leaves the page,
 * a button when the detail opens beside it - the same split the static site
 * makes, for the same reason.
 */
export default function ShipmentRow({
  s,
  labels,
  href,
  current,
  count = 1,
  resolved = false,
}: Props) {
  const tone = labels.tone?.[s.status] ?? "fine";
  const where = [
    s.oc_number || s.booking_ref || "no reference",
    route(s.shipment),
  ]
    .filter(Boolean)
    .join(" · ");

  // The band replaces the status tag on a mismatch: "Needs fixing" is already
  // obvious from the queue it sits in, and how urgently is what the reader
  // does not yet know.
  // A file that was wrong and is now right reads as its own thing. Showing it
  // as plain "Fine" loses the fact that somebody chased it, which is the part
  // a clerk wants credit for and the part an auditor wants to see.
  const badge = resolved ? (
    <span className="vis-tag fine">
      <StatusIcon status="OK" size={12} />
      Corrected
    </span>
  ) : s.severity ? (
    <span className={`vis-tag band ${s.severity}`}>
      <StatusIcon status={s.status} size={12} />
      {labels.band?.[s.severity] ?? s.severity}
    </span>
  ) : (
    <span className={`vis-tag ${tone}`}>
      <StatusIcon status={s.status} size={12} />
      {labels.status?.[s.status] ?? s.status}
    </span>
  );

  const inner = (
    <>
      <span className="who">{who(s)}</span>
      <span className="where">{where}</span>
      <span className={`issue ${tone}`}>
        {badge}
        {resolved ? "Corrected on a later draft" : issue(s, labels)}
        {count > 1 && (
          <span className="row-count">
            {count} emails
          </span>
        )}
      </span>
    </>
  );

  if (href) {
    return (
      <Link className={`row s-${tone}`} href={href as never}>
        {inner}
      </Link>
    );
  }
  return (
    <button
      type="button"
      className={`row s-${tone}`}
      data-id={s.email_id}
      aria-current={current ? "true" : "false"}
    >
      {inner}
    </button>
  );
}
