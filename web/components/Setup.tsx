/**
 * What the site says when it has nothing to show.
 *
 * A blank page and a stack trace both leave the reader guessing whether the
 * run is empty, the keys are wrong or the app is broken. This names which of
 * those it is and gives the command that fixes it.
 */
export default function Setup({
  title,
  detail,
  commands,
}: {
  title: string;
  detail: string;
  commands: string[];
}) {
  return (
    <div className="wrap">
      <header className="titlerow">
        <div>
          <h1>{title}</h1>
          <p className="date">{detail}</p>
        </div>
      </header>
      <main className="card" style={{ padding: "20px 22px" }}>
        <p style={{ marginTop: 0 }}>Run this, then reload:</p>
        <pre
          style={{
            margin: 0,
            padding: "14px 16px",
            borderRadius: "var(--r-lg)",
            background: "var(--fine-wash)",
            border: "1px solid var(--rule)",
            overflowX: "auto",
            fontSize: "14px",
            lineHeight: 1.7,
          }}
        >
          {commands.join("\n")}
        </pre>
      </main>
      <p className="foot">
        The static build in <code>out/site-demo</code> still works and needs no
        database.
      </p>
    </div>
  );
}
