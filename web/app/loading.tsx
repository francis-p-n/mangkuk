/**
 * What fills the screen while a page is being built on the server.
 *
 * Both pages are rendered per request, so there is a real wait - short, but
 * long enough that a blank screen reads as a broken link. A skeleton in the
 * shape of what is coming says "this is loading" without a spinner, and
 * because it matches the real layout the content does not jump when it
 * arrives.
 */
export default function Loading() {
  return (
    <div className="wrap" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading shipments…</span>
      <header className="titlerow">
        <div>
          <div className="sk sk-title" />
          <div className="sk sk-line" style={{ width: "18rem" }} />
        </div>
      </header>
      <div className="sk sk-bar" />
      <div className="card" style={{ marginTop: 18 }}>
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="sk-row">
            <div className="sk sk-line" style={{ width: `${60 - i * 4}%` }} />
            <div className="sk sk-line sk-sm" style={{ width: `${44 - i * 3}%` }} />
          </div>
        ))}
      </div>
    </div>
  );
}
