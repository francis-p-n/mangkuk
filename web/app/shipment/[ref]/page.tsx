import Link from "next/link";
import { notFound } from "next/navigation";
import { currentRun, one, NotConfigured } from "@/lib/supabase";
import { folderFor, folderState, referenceOf } from "@/lib/shipments";
import TopBar from "@/components/TopBar";
import Detail from "@/components/Detail";
import Setup from "@/components/Setup";
import StatusIcon from "@/components/StatusIcon";
import { who, route } from "@/lib/format";
import { isComparison } from "@/lib/graph";
import { Mail } from "lucide-react";

export const dynamic = "force-dynamic";

export const metadata = { title: "Shipment — Document checks" };

/**
 * One shipment's file: every email about it, and the verdict it currently
 * carries.
 *
 * The queue is a list of things to do; this is the thing itself. A clerk
 * arrives here from a row, or from a reference someone quoted at them on the
 * phone, and wants the whole correspondence in one place rather than a search
 * across a mailbox.
 */
export default async function ShipmentPage({
  params,
}: {
  params: Promise<{ ref: string }>;
}) {
  const { ref } = await params;
  const reference = decodeURIComponent(ref);

  let run, emails, detail;
  try {
    run = await currentRun();
    if (!run) {
      return (
        <Setup
          title="No run loaded yet"
          detail="Nothing is marked current in the database."
          local={["python run.py && python tools/demo_data.py",
                  "python tools/supabase_load.py"]}
          deployed={["Apply supabase/migrations/ in the SQL editor",
                     "python tools/supabase_load.py  (from your machine)"]}
        />
      );
    }
    emails = await folderFor(run.id, reference);
    if (!emails.length) notFound();

    // The comparison that decides the folder's state is the one shown open.
    // A file with no check in it - a booking confirmation and an arrival
    // notice, say - opens with nothing, and says so.
    const decisive = folderState(emails)?.decisive ?? null;
    detail = decisive ? await one(run.id, decisive.email_id) : null;
  } catch (e) {
    if (e instanceof NotConfigured) {
      return (
        <Setup
          title="Supabase is not configured"
          detail={`Not set: ${e.missing.join(" and ")}.`}
          local={["cp ../.env.example .env.local", "npm run dev"]}
          deployed={["Settings -> Environment Variables: add both",
                     "Redeploy with build cache off"]}
        />
      );
    }
    throw e;
  }

  const labels = run.labels;
  const head = emails[0];
  const folder = folderState(emails);
  const decisive = folder?.decisive ?? null;
  const resolved = folder?.resolved ?? false;

  return (
    <>
      <TopBar here="search" />
      <div className="wrap">
        <header className="titlerow">
          <div>
            <p className="crumb">
              <Link href={"/search" as never}>Every shipment</Link>
            </p>
            <h1>{who(head)}</h1>
            <p className="date">
              {referenceOf(head) ? `Shipment ${referenceOf(head)}` : "No reference"}
              {route(head.shipment) ? ` · ${route(head.shipment)}` : ""}
              {" · "}
              {emails.length === 1
                ? "one email"
                : `${emails.length} emails in this file`}
            </p>
          </div>
        </header>

        {resolved && (
          <p className="resolved">
            <StatusIcon status="OK" size={15} />
            This was corrected. A later draft for the same reference came back
            matching.
          </p>
        )}

        <main className="cols" id="results">
          <section className="card" aria-labelledby="thread-heading">
            <h2 className="listtop" id="thread-heading">
              The correspondence
            </h2>
            <ol className="thread">
              {emails.map((e) => {
                const isOpen = e.email_id === decisive?.email_id;
                // A booking confirmation belongs in the file, but it was
                // never compared - so it reports what kind of mail it is
                // rather than a verdict it does not have.
                const checked = isComparison(e);
                const tone = checked ? labels.tone?.[e.status] ?? "fine" : "idle";
                return (
                  <li key={e.email_id}>
                    <div className={`thread-item${isOpen ? " is-open" : ""}`}>
                      <Mail size={14} strokeWidth={2} aria-hidden="true" />
                      <div className="thread-body">
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
                          {isOpen && emails.length > 1 && " — shown below"}
                        </span>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
            {emails.length === 1 && (
              <p className="thread-note">
                Only one email mentions this reference. Anything else the
                carrier sends about it files itself here.
              </p>
            )}
          </section>

          <section className="card" aria-labelledby="shipment-name" aria-live="polite">
            {detail ? (
              <Detail s={detail} labels={labels} />
            ) : (
              <p className="allclear" style={{ padding: "28px 22px" }}>
                Nothing in this file has been compared.
              </p>
            )}
          </section>
        </main>

        <p className="foot">
          Nothing here is sent automatically. You send every email yourself.
        </p>
      </div>
    </>
  );
}
