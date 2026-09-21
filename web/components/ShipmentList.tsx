"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { ArrowUpRight } from "lucide-react";
import type { ListRow, Labels } from "@/lib/supabase";
import type { Result } from "@/lib/format";
import { useResult, PANEL_ID } from "@/lib/useResult";
import ShipmentRow from "./ShipmentRow";
import Detail from "./Detail";
import PanelSkeleton from "./PanelSkeleton";

/**
 * The list, and the shipment open beside it.
 *
 * One screen, so choosing a shipment moves one half of it. Every row used to
 * be a link to another route: the browser threw the list away, the server
 * re-rendered the whole page, and the reader watched a full-page loading
 * state to see a panel change - on a screen where the list they were reading
 * had not changed at all. The panel had been built for this from the start
 * and nothing ever linked to it, so it sat there saying "Choose a shipment on
 * the left" for good.
 *
 * What a click costs now is one row of JSON.
 */

export type Entry = {
  key: string;
  row: ListRow;
  /** The whole file, for when one check is not what the reader wanted. */
  href: string;
  count: number;
  resolved: boolean;
};

type Props = {
  runId: string;
  entries: Entry[];
  labels: Labels;
  /** Rendered on the server for the first paint, when the URL named one. */
  initial: Result | null;
  heading: string;
  empty: string;
};

/**
 * Up and down move through the queue.
 *
 * A clerk works a list of 46 the way they work a mailbox: next, next, next.
 * Making them travel to the mouse for each one is the difference between a
 * tool and a web page, and the rows are buttons, so this is the behaviour a
 * reader already expects from them.
 */
function useArrowKeys(
  ids: string[],
  openId: string | null,
  open: (id: string) => void
) {
  return (event: React.KeyboardEvent<HTMLUListElement>) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    if (!ids.length) return;

    const here = ids.indexOf(openId ?? "");
    const next =
      event.key === "ArrowDown"
        ? Math.min(here + 1, ids.length - 1)
        : Math.max(here - 1, 0);
    if (next === here) return;

    event.preventDefault();
    open(ids[next]);
    const buttons = event.currentTarget.querySelectorAll<HTMLButtonElement>(
      "button.row"
    );
    buttons[next]?.focus();
  };
}

export default function ShipmentList({
  runId,
  entries,
  labels,
  initial,
  heading,
  empty,
}: Props) {
  const { openId, shown, loading, failed, open } = useResult(runId, initial);
  const openEntry = entries.find((e) => e.row.email_id === openId);
  const onKeyDown = useArrowKeys(
    entries.map((e) => e.row.email_id),
    openId,
    open
  );

  // A link with ?id= in it arrives with a shipment open and its row three
  // screens down the list, which reads as the wrong one being shown. Only on
  // arrival: moving with the arrow keys focuses the row, and focusing already
  // scrolls it.
  const list = useRef<HTMLUListElement>(null);
  const landed = useRef(false);
  useEffect(() => {
    if (landed.current || !openId) return;
    landed.current = true;
    // After a frame, and centred. Fonts and the logo settle after first
    // paint, and a row brought minimally into view before that lands back
    // under the fold.
    requestAnimationFrame(() => {
      list.current
        ?.querySelector(`[data-id="${CSS.escape(openId)}"]`)
        ?.scrollIntoView({ block: "center" });
    });
  }, [openId]);

  return (
    <main className="cols" id="results">
      <section className="card" aria-labelledby="list-heading">
        <h2 className="listtop" id="list-heading">
          {heading}
        </h2>
        <ul ref={list} onKeyDown={onKeyDown}>
          {entries.length === 0 ? (
            <li className="allclear">{empty}</li>
          ) : (
            entries.map((e) => (
              <li key={e.key}>
                <ShipmentRow
                  s={e.row}
                  labels={labels}
                  current={openId === e.row.email_id}
                  count={e.count}
                  resolved={e.resolved}
                  onSelect={open}
                />
              </li>
            ))
          )}
        </ul>
      </section>

      <section
        id={PANEL_ID}
        className="card"
        aria-labelledby="shipment-name"
        aria-live="polite"
        aria-busy={loading}
      >
        {loading ? (
          <PanelSkeleton />
        ) : shown ? (
          <>
            {openEntry && (
              <p className="panel-jump">
                <Link href={openEntry.href as never}>
                  {openEntry.count > 1
                    ? `Open the whole file — ${openEntry.count} emails`
                    : "Open the whole file"}
                  <ArrowUpRight size={14} strokeWidth={2.25} aria-hidden="true" />
                </Link>
              </p>
            )}
            <Detail s={shown} labels={labels} />
          </>
        ) : (
          <p className="allclear" style={{ padding: "28px 22px" }}>
            {failed ??
              "Choose a shipment to see the seven details that were checked."}
          </p>
        )}
      </section>
    </main>
  );
}
