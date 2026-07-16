import { v } from "convex/values";
import { mutation } from "./_generated/server";

/**
 * Service mutation called by the Python livekit-agents worker.
 * Protected by CONVEX_SERVICE_SECRET env var — not user auth.
 */
export const ping = mutation({
  args: {
    secret: v.string(),
  },
  handler: (_ctx, { secret }) => {
    const expected = process.env.CONVEX_SERVICE_SECRET;
    if (!expected || secret !== expected) {
      throw new Error("unauthorized");
    }
    return { ok: true, timestamp: Date.now() };
  },
});
