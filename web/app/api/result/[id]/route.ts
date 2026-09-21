import { NextResponse } from "next/server";
import { one, NotConfigured } from "@/lib/supabase";

/**
 * One shipment's full record, for the panel beside the list.
 *
 * Choosing a shipment used to be a page navigation: the whole route
 * re-rendered, the list was thrown away and drawn again, and the reader
 * watched a loading state to see seven rows of text change. The list and the
 * panel are one screen, so only the panel should move.
 *
 * Server-side, like every other query here, so the browser gets the one row
 * it is about to draw rather than a database client and a key.
 */
export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const runId = new URL(request.url).searchParams.get("run");
  if (!runId) {
    return NextResponse.json({ error: "no run given" }, { status: 400 });
  }

  try {
    const result = await one(runId, id);
    if (!result) {
      return NextResponse.json({ error: `no ${id} in this run` }, { status: 404 });
    }
    return NextResponse.json(result);
  } catch (e) {
    if (e instanceof NotConfigured) {
      return NextResponse.json({ error: e.message }, { status: 503 });
    }
    const message = e instanceof Error ? e.message : "unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
