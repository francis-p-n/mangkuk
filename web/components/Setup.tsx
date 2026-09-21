/**
 * What the site says when it has nothing to show.
 *
 * A blank page and a stack trace both leave the reader guessing whether the
 * run is empty, the keys are wrong or the app is broken. This names which of
 * those it is and what fixes it.
 *
 * Deployed and local need different answers. On Vercel there is no .env.local
 * to copy - the keys live in project settings and only take effect on the next
 * deploy - and telling a person to run `npm run dev` on a page they opened in
 * production is the kind of instruction that wastes an afternoon.
 */
export default function Setup({
  title,
  detail,
  local,
  deployed,
}: {
  title: string;
  detail: string;
  local: string[];
  deployed: string[];
}) {
  const onVercel = Boolean(process.env.VERCEL);
  const steps = onVercel ? deployed : local;

  return (
    <div className="wrap">
      <header className="titlerow">
        <div>
          <h1>{title}</h1>
          <p className="date">{detail}</p>
        </div>
      </header>
      <main className="card" style={{ padding: "20px 22px" }}>
        <p style={{ marginTop: 0 }}>
          {onVercel ? "In the Vercel project:" : "Run this, then reload:"}
        </p>
        <ol style={{ margin: 0, paddingLeft: "20px", lineHeight: 1.9 }}>
          {steps.map((s) => (
            <li key={s}>
              <code>{s}</code>
            </li>
          ))}
        </ol>
      </main>
      <p className="foot">
        {onVercel
          ? "Environment variables only take effect on the next deploy."
          : "The static build in out/site-demo still works and needs no database."}
      </p>
    </div>
  );
}
