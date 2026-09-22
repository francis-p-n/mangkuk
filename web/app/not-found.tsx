import Link from "next/link";
import TopBar from "@/components/TopBar";

/**
 * A reference that is not in this run.
 *
 * Without this the reader gets Next's own 404: a black page, "This page could
 * not be found", no bar, no way back. That is a dead end in the middle of a
 * product, and the commonest way to arrive at it is not a broken link - it is
 * someone typing a reference they were given on the phone, or following a
 * link to a shipment that was in last week's run and is not in this one.
 *
 * So it says which of those it probably is, and offers the search rather than
 * leaving the reader to find it.
 */
export const metadata = { title: "Not found — Document checks" };

export default function NotFound() {
  return (
    <>
      <TopBar here="search" />
      <div className="wrap">
        <header className="titlerow">
          <div>
            <h1>No such shipment</h1>
            <p className="date">
              Nothing in this run carries that reference.
            </p>
          </div>
        </header>

        <main className="card" style={{ padding: "22px" }}>
          <p style={{ marginTop: 0 }}>
            Two things usually explain it: the reference belongs to an earlier
            run than the one loaded here, or a character went astray on the way
            from a phone call to the address bar. Searching for part of it —
            the customer, the port, the vessel — finds it if it is here at all.
          </p>

          <div className="buttons">
            <Link className="btn go" href={"/search" as never}>
              Search every shipment
            </Link>
            <Link className="btn" href={"/" as never}>
              Back to Today
            </Link>
          </div>
        </main>

        <p className="foot">
          Nothing here is sent automatically. You send every email yourself.
        </p>
      </div>
    </>
  );
}
