import Link from "next/link";
import { currentRun, search, one, NotConfigured, PAGE } from "@/lib/supabase";
import ShipmentRow, { issue } from "@/components/ShipmentRow";
import Detail from "@/components/Detail";
import Setup from "@/components/Setup";

export const dynamic = "force-dynamic";

const FILTERS = [
  { value: "ALL", label: "Everything" },
  { value: "MISMATCH", label: "Needs fixing" },
  { value: "NEEDS_REVIEW", label: "Needs you to look" },
  { value: "OK", label: "Fine" },
];

export default async function Search({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; status?: string; id?: string }>;
}) {
  const sp = await searchParams;
  const q = sp.q ?? "";
  const status = sp.status ?? "ALL";

  let run, rows, selected;
  try {
    run = await currentRun();
    if (!run) {
      return (
        <Setup
          title="No run loaded yet"
          detail="Nothing is marked current in the database."
          local={[
            "python run.py && python tools/demo_data.py",
            "python tools/supabase_load.py",
          ]}
          deployed={[
            "Apply supabase/migrations/0001_results.sql in the SQL editor",
            "python tools/supabase_load.py  (from your machine)",
          ]}
        />
      );
    }
    rows = await search(run.id, { q, status });
    // An id in the query string opens that shipment even when the current
    // filter would not list it - following a link from Today must always
    // land on the thing the link named.
    selected = sp.id ? await one(run.id, sp.id) : null;
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

  const labels = run.labels;
  const keep = (extra: Record<string, string>) => {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (status !== "ALL") p.set("status", status);
    for (const [k, v] of Object.entries(extra)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    const s = p.toString();
    return (s ? `/search?${s}` : "/search") as never;
  };

  return (
    <div className="wrap">
      <header className="titlerow">
        <div>
          <h1>Every shipment</h1>
          <p className="date">
            {rows.length === PAGE
              ? `The first ${PAGE}. Narrow the search to see the rest.`
              : rows.length === run.totals.emails
                ? `All ${rows.length} checked.`
                : `${rows.length} of ${run.totals.emails} match.`}
          </p>
        </div>
        <nav className="whoami" aria-label="Sections">
          <Link href={"/" as never}>Today</Link>
        </nav>
      </header>

      <form className="jump" action="/search" role="search">
        <label className="sr-only" htmlFor="q">
          Search every shipment
        </label>
        <input
          type="search"
          id="q"
          name="q"
          defaultValue={q}
          placeholder="Find a customer, OC number, port or vessel"
        />
        {status !== "ALL" && <input type="hidden" name="status" value={status} />}
        <button className="btn" type="submit">
          Search
        </button>
      </form>

      <nav className="bandbar" aria-label="Filter by what needs doing">
        {FILTERS.map((f) => (
          <Link
            key={f.value}
            href={keep({ status: f.value === "ALL" ? "" : f.value, id: "" })}
            aria-current={status === f.value ? "true" : undefined}
            style={{ fontWeight: status === f.value ? 600 : 400 }}
          >
            {f.label}
          </Link>
        ))}
      </nav>

      <main className="cols" id="results">
        <section className="card" aria-labelledby="list-heading">
          <h2 className="listtop" id="list-heading">
            {status === "ALL" ? "Every shipment" : "Filtered"}
          </h2>
          <ul>
            {rows.length === 0 ? (
              <li className="allclear">
                Nothing matches {q ? `“${q}”` : "that filter"}.
              </li>
            ) : (
              rows.map((s) => (
                <li key={s.email_id}>
                  <ShipmentRow
                    s={s}
                    labels={labels}
                    href={keep({ id: s.email_id })}
                    current={selected?.email_id === s.email_id}
                  />
                </li>
              ))
            )}
          </ul>
        </section>

        <section className="card" aria-labelledby="shipment-name" aria-live="polite">
          {selected ? (
            <Detail s={selected} labels={labels} />
          ) : (
            <p className="allclear" style={{ padding: "28px 22px" }}>
              Choose a shipment to see what was checked.
            </p>
          )}
        </section>
      </main>

      <p className="foot">
        {selected
          ? issue(selected, labels)
          : "Nothing here is sent automatically. You send every email yourself."}
      </p>
    </div>
  );
}
