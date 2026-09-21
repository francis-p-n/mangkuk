"use client";

/**
 * What the reader sees when a page could not be built.
 *
 * Without this, a database that is unreachable for a moment produces a stack
 * trace in production and nothing actionable. A clerk cannot fix Postgres,
 * but they can press a button, and they need to know the queue they were
 * working is not lost - so the one thing this does not do is imply the data
 * is gone.
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="wrap">
      <header className="titlerow">
        <div>
          <h1>Could not load the checks</h1>
          <p className="date">
            The shipments are safe. This page could not reach them just now.
          </p>
        </div>
      </header>

      <main className="card" style={{ padding: "22px" }}>
        <p style={{ marginTop: 0 }}>
          Nothing has been changed or lost. Trying again usually works — the
          run is stored in the database and this page is only reading it.
        </p>

        <div className="buttons">
          <button type="button" className="btn go" onClick={reset}>
            Try again
          </button>
          <a className="btn" href="/">
            Back to Today
          </a>
        </div>

        {/* The digest is what a maintainer needs to find this in the logs.
            It is not an explanation, so it does not pretend to be one. */}
        {error.digest && (
          <p className="foot" style={{ textAlign: "left", marginBottom: 0 }}>
            Reference for support: <code>{error.digest}</code>
          </p>
        )}
      </main>
    </div>
  );
}
