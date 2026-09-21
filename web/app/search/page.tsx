import Link from "next/link";
import { currentRun, search, one, NotConfigured, PAGE } from "@/lib/supabase";
import ShipmentRow, { issue } from "@/components/ShipmentRow";
import Detail from "@/components/Detail";
import Setup from "@/components/Setup";
import StatusIcon from "@/components/StatusIcon";
import { LayoutList, Search as SearchIcon } from "lucide-react";
import TopBar from "@/components/TopBar";

export const dynamic = "force-dynamic";

export const metadata = { title: "Every shipment — Document checks" };

const FILTERS = [
  { value: "ALL", label: "Everything", tone: "f-all" },
  { value: "MISMATCH", label: "Needs fixing", tone: "f-mismatch" },
  { value: "NEEDS_REVIEW", label: "Needs you to look", tone: "f-review" },
  { value: "OK", label: "Fine", tone: "f-ok" },
] as const;

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
    <>
      <TopBar here="search" />
      <div className="wrap">
      <a className="skip" href="#results">
        Skip to the results
      </a>

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
          <SearchIcon size={15} strokeWidth={2.25} aria-hidden="true" />
          Search
        </button>
      </form>

      <nav className="filters" aria-label="Filter by what needs doing">
        {FILTERS.map((f) => {
          // The run's own totals, so the control says how much is behind each
          // option before it is clicked. "Fine" counts comparison requests,
          // not every email, which is what the rest of the site means by it.
          const n =
            f.value === "MISMATCH" ? run.totals.mismatch
            : f.value === "NEEDS_REVIEW" ? run.totals.review
            : f.value === "OK" ? run.totals.ok
            : run.totals.comparisons;
          return (
            <Link
              key={f.value}
              className={f.tone}
              href={keep({ status: f.value === "ALL" ? "" : f.value, id: "" })}
              aria-current={status === f.value ? "true" : undefined}
            >
              {f.value === "ALL" ? (
                <LayoutList size={14} strokeWidth={2.25} aria-hidden="true" />
              ) : (
                <StatusIcon status={f.value} />
              )}
              {f.label}
              <span className="n">{n}</span>
            </Link>
          );
        })}
      </nav>

      <p className="sr-only" role="status" aria-live="polite">
        {rows.length} shipment{rows.length === 1 ? "" : "s"} shown.
      </p>

      <main className="cols" id="results">
        <section className="card" aria-labelledby="list-heading">
          {/* Name what is in the list, not that a filter is on. "Filtered"
              tells the reader something they already did; the label of the
              filter tells them what they are looking at. */}
          <h2 className="listtop" id="list-heading">
            {FILTERS.find((f) => f.value === status)?.label ?? "Every shipment"}
            {q ? ` matching “${q}”` : ""}
          </h2>
          <ul>
            {rows.length === 0 ? (
              <li className="allclear">
                {q
                  ? `Nothing matches “${q}”. Try a customer name, an OC number, a port or a vessel.`
                  : "Nothing in this filter. Choose Everything to see the whole run."}
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
              {sp.id
                ? `There is no shipment ${sp.id} in this run.`
                : "Choose a shipment on the left to see the seven details that were checked."}
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
    </>
  );
}
