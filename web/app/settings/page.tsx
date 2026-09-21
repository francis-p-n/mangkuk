import { currentRun, NotConfigured } from "@/lib/supabase";
import TopBar from "@/components/TopBar";
import Setup from "@/components/Setup";

export const dynamic = "force-dynamic";

export const metadata = { title: "Settings — Document checks" };

export default async function Settings() {
  let run = null;
  try {
    run = await currentRun();
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
          ]}
        />
      );
    }
    throw e;
  }

  return (
    <>
      <TopBar here="settings" />
      <div className="wrap">
        <header className="titlerow">
          <div>
            <h1>Settings</h1>
            <p className="date">Where the checks come from, and how they get here.</p>
          </div>
        </header>

        <main>
          <section className="card setting">
            <h2>The run on screen</h2>
            {run ? (
              <dl className="facts">
                <dt>Checked</dt>
                <dd>{new Date(run.generated_at).toLocaleString()}</dd>
                <dt>Source file</dt>
                <dd>
                  <code>{run.source ?? "unknown"}</code>
                  {run.source?.includes("demo") && (
                    <span className="note-inline">
                      names and references replaced with invented ones
                    </span>
                  )}
                </dd>
                <dt>Emails</dt>
                <dd>{run.totals.emails}</dd>
                <dt>Drafts checked</dt>
                <dd>{run.totals.comparisons}</dd>
              </dl>
            ) : (
              <p className="nothing">No run is loaded.</p>
            )}
            <p className="setting-foot">
              A new run replaces this one the moment it finishes loading. This
              page reads it; nothing here changes it.
            </p>
          </section>

          <section className="card setting">
            <h2>Where the mail comes from</h2>
            <p>
              The checker reads a batch of emails and their attachments, then
              writes its verdicts to this database. Two sources work today.
            </p>
            <dl className="facts">
              <dt>A folder</dt>
              <dd>
                <code>python run.py</code> — reads <code>data/</code> on the
                machine running it. This is what produced the run above.
              </dd>
              <dt>A server</dt>
              <dd>
                <code>python run.py --source http://host:8080</code> — pulls the
                batch over HTTP instead.
              </dd>
            </dl>
          </section>

          {/*
            A live mailbox is on the roadmap and is not built. A button here
            that opened a Google consent screen and then did nothing would be
            worse than no button: it would suggest the desk's real mail was
            being read, which is the one thing a clerk must never be wrong
            about. So this says plainly where it stands.
          */}
          <section className="card setting">
            <h2>
              Connect a mailbox
              <span className="pill-soon">Not built yet</span>
            </h2>
            <p>
              Reading a live inbox directly — Gmail, Outlook or IMAP — is the
              next thing on the roadmap, and it is not here yet. Nothing on this
              page is connected to a real mailbox, and no mail is being read.
            </p>
            <p className="setting-foot">
              Until then, the batch is collected by whoever runs the checker,
              and every correction email is still sent by a person from their
              own mailbox. Nothing is sent automatically, by design.
            </p>
          </section>
        </main>

        <p className="foot">
          Nothing here is sent automatically. You send every email yourself.
        </p>
      </div>
    </>
  );
}
