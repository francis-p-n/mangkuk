"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Result } from "./format";

/**
 * Open one shipment beside the list it was chosen from.
 *
 * Shared by the search list and by one file's correspondence, because both
 * are the same gesture: a list on the left, the thing itself on the right,
 * and a click that should move only the right. Neither of them should cost a
 * page.
 *
 * Three things this has to get right, and all three are the reason it is not
 * three lines of `fetch` at each call site:
 *
 *  - Rows already read are kept, so going back to one is instant.
 *  - The newest click wins. A slow answer for a shipment the reader has
 *    already clicked past must never overwrite the one they are looking at.
 *  - The URL follows the selection, so the screen can still be shared,
 *    reloaded or bookmarked. `replaceState` rather than a router push: this
 *    is not a new page, and it should not cost a back-button press to leave.
 */
export function useResult(runId: string, initial: Result | null) {
  const [openId, setOpenId] = useState<string | null>(initial?.email_id ?? null);
  const [shown, setShown] = useState<Result | null>(initial);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const seen = useRef(new Map<string, Result>());
  const wanted = useRef<string | null>(initial?.email_id ?? null);

  useEffect(() => {
    if (initial) seen.current.set(initial.email_id, initial);
  }, [initial]);

  const open = useCallback(
    async (emailId: string) => {
      wanted.current = emailId;
      setOpenId(emailId);
      setFailed(null);

      try {
        const url = new URL(window.location.href);
        url.searchParams.set("id", emailId);
        window.history.replaceState(null, "", url);
      } catch {
        // A URL the browser will not let us rewrite is not a reason to
        // refuse to show the shipment.
      }

      const cached = seen.current.get(emailId);
      if (cached) {
        setShown(cached);
        setLoading(false);
        return;
      }

      setLoading(true);
      try {
        const res = await fetch(
          `/api/result/${encodeURIComponent(emailId)}?run=${encodeURIComponent(runId)}`
        );
        if (!res.ok) throw new Error(String(res.status));
        const data = (await res.json()) as Result;
        seen.current.set(emailId, data);
        if (wanted.current !== emailId) return;
        setShown(data);
      } catch {
        if (wanted.current !== emailId) return;
        setShown(null);
        setFailed("That shipment could not be read. Try again in a moment.");
      } finally {
        if (wanted.current === emailId) setLoading(false);
      }
    },
    [runId]
  );

  return { openId, shown, loading, failed, open };
}
