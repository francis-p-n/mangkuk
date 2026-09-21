"use client";

import { useState } from "react";
import { ChevronDown, Mail, Paperclip } from "lucide-react";
import type { Result } from "@/lib/format";

/**
 * The message the verdict is about.
 *
 * Underneath the summary rather than above it, because the summary is what a
 * clerk came for: what is wrong, how badly, and what to send. The email is
 * what they check when they want to see what was actually asked before acting
 * on a conclusion about it.
 *
 * Collapsed by default for the same reason. Five hundred words of "Hi Najiha,
 * attached are the SI and draft BL" between the verdict and the correction
 * email would push the thing being worked off the screen.
 */
export default function EmailPanel({ s }: { s: Result }) {
  const [open, setOpen] = useState(false);
  const body = (s.body ?? "").trim();
  const attachments = (s.documents ?? []).filter((d) => d.path);

  if (!body && !attachments.length) return null;

  // A line to stand in for the message when it is closed - enough to recognise
  // it by, not enough to read instead of opening it.
  const preview = body.replace(/\s+/g, " ").slice(0, 96);

  return (
    <section className="mail">
      <h3 id="mail-heading">The email</h3>

      <button
        type="button"
        className="mail-head"
        aria-expanded={open}
        aria-controls="mail-body"
        onClick={() => setOpen((v) => !v)}
      >
        <Mail size={16} strokeWidth={2} aria-hidden="true" className="mail-icon" />
        <span className="mail-meta">
          <span className="mail-from">{s.sender ?? "unknown sender"}</span>
          <span className="mail-subject">{s.subject ?? "(no subject)"}</span>
          {!open && preview && <span className="mail-preview">{preview}…</span>}
        </span>
        <ChevronDown
          size={17}
          strokeWidth={2.25}
          aria-hidden="true"
          className={`mail-chev${open ? " is-open" : ""}`}
        />
      </button>

      {open && (
        <div id="mail-body" className="mail-body">
          {/* Preformatted: these are plain-text messages whose line breaks and
              indentation are the only structure they have. Reflowing them
              turns a quoted table of figures into a paragraph. */}
          {body ? (
            <pre>{body}</pre>
          ) : (
            <p className="nothing">This email had no body text.</p>
          )}

          {attachments.length > 0 && (
            <ul className="mail-files">
              {attachments.map((d) => (
                <li key={d.path}>
                  <Paperclip size={13} strokeWidth={2.25} aria-hidden="true" />
                  <span className="mail-file-name">
                    {d.path?.split("/").pop()}
                  </span>
                  <span className="mail-file-role">
                    {d.role}
                    {d.readable === false && " — could not be read"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
