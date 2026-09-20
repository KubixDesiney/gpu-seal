import { readCommittedBundle } from "../../../lib/evidence-bundles";

// Serves one committed bundle to the in-browser inspector. GET only: no other
// method is exported, so nothing can be sent to this route, and it accepts no
// path, only an id that must match a committed run directory.
export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
): Promise<Response> {
  const { id } = await context.params;
  const bundle = readCommittedBundle(id);
  if (bundle === null) {
    return new Response("No such committed bundle.", {
      status: 404,
      headers: { "content-type": "text/plain; charset=utf-8" },
    });
  }
  return new Response(bundle, {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "public, max-age=300",
      "x-content-type-options": "nosniff",
      // The portal is pre-alpha and unindexed; a raw bundle URL must not be
      // the way around that.
      "x-robots-tag": "noindex, nofollow",
    },
  });
}
