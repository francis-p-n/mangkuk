"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import type { ListRow, Labels } from "@/lib/supabase";
import type { Result } from "@/lib/format";
import { useResult } from "@/lib/useResult";
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

  return (
    <main className="cols" id="results">
      <section className="card" aria-labelledby="list-heading">
        <h2 className="listtop" id="list-heading">
          {heading}
        </h2>
        <ul>
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
              "Choose a shipment on the left to see the seven details that were checked."}
          </p>
        )}
      </section>
    </main>
  );
}
