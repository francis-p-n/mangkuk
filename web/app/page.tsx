import Link from "next/link";
import { currentRun, byStatus, NotConfigured } from "@/lib/supabase";
import ShipmentRow from "@/components/ShipmentRow";
import Setup from "@/components/Setup";

// Verdicts change when the pipeline reloads the table, not when this builds,
// so the page is rendered per request. A reload after a load shows the new
// run with no redeploy.
export const dynamic = "force-dynamic";

export const metadata = { title: "Today — Document checks" };

const SHOWN = 6; // a screenful; the rest is one click away

export default async function Today() {
  let run, fix, look;
  try {
    run = await currentRun();
    if (!run) {
      return (
        <Setup
          title="No run loaded yet"
          detail="The database is reachable, but nothing is marked current."
          local={[
            "python run.py && python tools/demo_data.py",
            "python tools/supabase_load.py",
          ]}
          deployed={[
            "Apply supabase/migrations/0001_results.sql in the SQL editor",
            "python run.py && python tools/demo_data.py",
            "python tools/supabase_load.py  (from your machine)",
          ]}
        />
      );
    }
    [fix, look] = await Promise.all([
      byStatus(run.id, "MISMATCH"),
      byStatus(run.id, "NEEDS_REVIEW"),
    ]);
  } catch (e) {
    if (e instanceof NotConfigured) {
      return (
        <Setup
          title="Supabase is not configured"
          detail={`Not set: ${e.missing.join(" and ")}.`}
          local={["cp ../.env.example .env.local", "npm run dev"]}
          deployed={[
            "Settings -> Environment Variables: add both, scope Production",
            "Deployments -> Redeploy, with 'Use existing Build Cache' OFF",
            "Names must match exactly - a trailing space counts",
          ]}
        />
      );
    }
    throw e;
  }

  const t = run.totals;
  const labels = run.labels;
  const needsWork = t.mismatch + t.review;

  const queues = [
    { id: "fix", heading: "Needs fixing", rows: fix, status: "MISMATCH" },
    { id: "look", heading: "Needs you to look", rows: look, status: "NEEDS_REVIEW" },
  ];

  return (
    <div className="wrap">
      <a className="skip" href="#work">
        Skip to what needs doing
      </a>

      <header className="titlerow">
        <div>
          <h1>Today</h1>
          <p className="date">
            {t.comparisons} drafts from {t.emails} emails, checked{" "}
            {run.generated_at.slice(0, 10)}.
          </p>
        </div>
      </header>

      <p className="headline">
        {needsWork ? (
          <>
            <b>{needsWork}</b> shipments need you today. The other{" "}
            <b className="fine">{t.ok}</b> match the instruction on every
            detail.
          </>
        ) : (
          <>
            Nothing needs you today. All <b className="fine">{t.ok}</b> drafts
            match their instruction.
          </>
        )}
      </p>

      <p className="orient">
        Every draft bill of lading below was compared against the shipping
        instruction that ordered it. <b>Needs fixing</b> means a detail
        disagrees. <b>Needs you to look</b> means it could not be checked, so
        nothing was guessed.
      </p>

      <form className="jump" action="/search" role="search">
        <label className="sr-only" htmlFor="q">
          Search every shipment
        </label>
        <input
          type="search"
          id="q"
          name="q"
          placeholder="Find a customer, OC number, port or vessel"
        />
        <button className="btn" type="submit">
          Search all <span className="num">{t.comparisons}</span>
        </button>
      </form>

      <main id="work">
        {queues.map((qu) => (
          <section key={qu.id} className="queue" aria-labelledby={`${qu.id}-heading`}>
            <div className="queue-head">
              <h2 id={`${qu.id}-heading`}>{qu.heading}</h2>
              <span className={`count ${qu.id} num`}>{qu.rows.length}</span>
              {qu.rows.length > 0 && (
                <Link className="more" href={`/search?status=${qu.status}` as never}>
                  {qu.rows.length > SHOWN
                    ? `See all ${qu.rows.length}`
                    : "Open the list"}
                </Link>
              )}
            </div>

            {/* The queue arrives worst-first, so the bar just names the bands
                it is already sorted by. Empty bands are left out rather than
                shown as zero: a pile with nothing in it is not news. */}
            {qu.id === "fix" && (
              <p className="bandbar">
                {run.bands
                  .map((b) => ({ ...b, n: run.severity[b.name] ?? 0 }))
                  .filter((b) => b.n)
                  .map((b) => (
                    <span key={b.name} className={b.name}>
                      <b>{b.n}</b>{" "}
                      {(labels.band?.[b.name] ?? b.name).toLowerCase()} —{" "}
                      {b.consequence}
                    </span>
                  ))}
              </p>
            )}

            <div className="card">
              <ul>
                {qu.rows.length === 0 ? (
                  <li className="allclear">
                    {qu.status === "MISMATCH"
                      ? "No draft disagrees with its instruction today."
                      : "Nothing needed a person today."}
                  </li>
                ) : (
                  qu.rows.slice(0, SHOWN).map((s) => (
                    <li key={s.email_id}>
                      <ShipmentRow
                        s={s}
                        labels={labels}
                        href={`/search?id=${encodeURIComponent(s.email_id)}`}
                      />
                    </li>
                  ))
                )}
              </ul>
            </div>
          </section>
        ))}

        <p className="settled">
          <b>{t.ok} drafts are fine.</b>{" "}
          <span>
            All seven details matched, so there is nothing to do.
          </span>
          <Link href={"/search?status=OK" as never}>Look anyway</Link>
        </p>
      </main>

      <p className="foot">
        Nothing here is sent automatically. You send every email yourself.
      </p>
    </div>
  );
}
