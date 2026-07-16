import { v } from "convex/values";
import { mutation } from "./_generated/server";

/**
 * Overwatch agent mutations — called by the Python LiveKit worker (Reflex
 * agent) when it detects critical danger. Protected by
 * CONVEX_SERVICE_SECRET, NOT user auth (the agent has no user session).
 *
 * Flow (agent side):
 *   1. agent mints a spectator LiveKit token + builds a spectator URL
 *   2. agent calls startForAgent -> this resolves the blind user's linked
 *      guardian and creates an active overwatch session, returning the
 *      guardian's WhatsApp number + name
 *   3. agent sends the spectator URL to that number via GoWA (WhatsApp)
 *   4. agent calls markWhatsappSent so the dashboard can show delivery status
 */

function assertSecret(secret: string) {
  const expected = process.env.CONVEX_SERVICE_SECRET;
  if (!expected || secret !== expected) {
    throw new Error("unauthorized");
  }
}

// Start an Overwatch session on behalf of the agent. Returns the guardian's
// contact info so the agent can send the WhatsApp alert. Idempotent: any
// existing active session for this blind user is ended first.
export const startForAgent = mutation({
  args: {
    secret: v.string(),
    blindUserProfileId: v.id("userProfiles"),
    livekitRoomName: v.string(),
    spectatorUrl: v.string(),
    reason: v.optional(v.string()),
  },
  returns: v.object({
    sessionId: v.id("overwatchSessions"),
    guardianFullName: v.optional(v.string()),
    guardianWhatsappNumber: v.optional(v.string()),
  }),
  handler: async (ctx, args) => {
    assertSecret(args.secret);

    const blindUser = await ctx.db.get(args.blindUserProfileId);
    if (!blindUser) {
      throw new Error("blind user profile not found");
    }

    // End any existing active session for this blind user first so only one
    // Overwatch session is live at a time.
    const userSessions = await ctx.db
      .query("overwatchSessions")
      .withIndex("by_blindUserProfileId", (q) =>
        q.eq("blindUserProfileId", blindUser._id)
      )
      .collect();
    const existing = userSessions.find((s) => s.status === "active");
    if (existing) {
      await ctx.db.patch(existing._id, {
        status: "ended",
        endedAt: Date.now(),
      });
    }

    // Resolve the linked guardian (if any) for the WhatsApp alert.
    let guardianFullName: string | undefined;
    let guardianWhatsappNumber: string | undefined;
    if (blindUser.guardianProfileId) {
      const guardian = await ctx.db.get(blindUser.guardianProfileId);
      if (guardian) {
        guardianFullName = guardian.fullName;
        guardianWhatsappNumber = guardian.whatsappNumber;
      }
    }

    const sessionId = await ctx.db.insert("overwatchSessions", {
      blindUserProfileId: blindUser._id,
      guardianProfileId: blindUser.guardianProfileId,
      livekitRoomName: args.livekitRoomName,
      status: "active",
      reason: args.reason,
      spectatorUrl: args.spectatorUrl,
      guardianWhatsappNumber,
      // whatsappSent stays unset until the agent reports the send result.
      startedAt: Date.now(),
    });

    return { sessionId, guardianFullName, guardianWhatsappNumber };
  },
});

// Record whether the WhatsApp alert was delivered. Called by the agent after
// its GoWA send attempt (success or failure).
export const markWhatsappSent = mutation({
  args: {
    secret: v.string(),
    sessionId: v.id("overwatchSessions"),
    sent: v.boolean(),
  },
  returns: v.null(),
  handler: async (ctx, args) => {
    assertSecret(args.secret);
    await ctx.db.patch(args.sessionId, { whatsappSent: args.sent });
    return null;
  },
});
