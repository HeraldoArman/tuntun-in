import { ConvexError, v } from "convex/values";
import type { MutationCtx, QueryCtx } from "./_generated/server";
import { mutation, query } from "./_generated/server";
import { authComponent } from "./auth";

/**
 * Overwatch Mode — emergency spectator sessions.
 *
 * When the AI agent detects critical danger, it creates an overwatch session
 * with a LiveKit room. The guardian receives a WebRTC link and can view the
 * blind user's camera live and guide them verbally.
 */

type Ctx = QueryCtx | MutationCtx;

async function getMyProfile(ctx: Ctx) {
  const authUser = await authComponent.safeGetAuthUser(ctx);
  if (!authUser) {
    throw new ConvexError("Not authenticated");
  }
  const profile = await ctx.db
    .query("userProfiles")
    .withIndex("by_authUserId", (q) => q.eq("authUserId", authUser._id))
    .first();
  if (!profile) {
    throw new ConvexError("Profile not found");
  }
  return profile;
}

// Guardian: list active overwatch sessions for all linked blind users
export const getActiveForGuardian = query({
  args: {},
  returns: v.array(
    v.object({
      _id: v.id("overwatchSessions"),
      blindUserProfileId: v.id("userProfiles"),
      blindUserFullName: v.string(),
      livekitRoomName: v.string(),
      status: v.union(v.literal("active"), v.literal("ended")),
      startedAt: v.number(),
    })
  ),
  handler: async (ctx) => {
    const guardian = await getMyProfile(ctx);
    if (guardian.role !== "guardian") {
      return [];
    }

    const links = await ctx.db
      .query("guardianLinks")
      .withIndex("by_guardianProfileId", (q) =>
        q.eq("guardianProfileId", guardian._id)
      )
      .collect();

    const blindUserIds = links.map((l) => l.blindUserProfileId);
    if (blindUserIds.length === 0) {
      return [];
    }

    const sessions = await Promise.all(
      blindUserIds.map(async (blindUserId) => {
        const userSessions = await ctx.db
          .query("overwatchSessions")
          .withIndex("by_blindUserProfileId", (q) =>
            q.eq("blindUserProfileId", blindUserId)
          )
          .collect();
        const active = userSessions.find((s) => s.status === "active");
        if (!active) {
          return null;
        }
        const blindUser = await ctx.db.get(blindUserId);
        return {
          _id: active._id,
          blindUserProfileId: blindUserId,
          blindUserFullName: blindUser?.fullName ?? "Unknown",
          livekitRoomName: active.livekitRoomName,
          status: active.status,
          startedAt: active.startedAt,
        };
      })
    );

    return sessions.filter((s): s is NonNullable<typeof s> => s !== null);
  },
});

// Blind user: get my active overwatch session (if any)
export const getMyActiveSession = query({
  args: {},
  returns: v.union(
    v.object({
      _id: v.id("overwatchSessions"),
      livekitRoomName: v.string(),
      status: v.union(v.literal("active"), v.literal("ended")),
      startedAt: v.number(),
    }),
    v.null()
  ),
  handler: async (ctx) => {
    const blindUser = await getMyProfile(ctx);
    if (blindUser.role !== "blind_user") {
      return null;
    }

    const userSessions = await ctx.db
      .query("overwatchSessions")
      .withIndex("by_blindUserProfileId", (q) =>
        q.eq("blindUserProfileId", blindUser._id)
      )
      .collect();
    const session = userSessions.find((s) => s.status === "active");

    if (!session) {
      return null;
    }
    return {
      _id: session._id,
      livekitRoomName: session.livekitRoomName,
      status: session.status,
      startedAt: session.startedAt,
    };
  },
});

// Start an overwatch session (called by the agent or blind user in demo)
export const startSession = mutation({
  args: {
    livekitRoomName: v.string(),
  },
  returns: v.id("overwatchSessions"),
  handler: async (ctx, args) => {
    const blindUser = await getMyProfile(ctx);
    if (blindUser.role !== "blind_user") {
      throw new ConvexError("Only blind users can start overwatch sessions");
    }

    // End any existing active session first
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

    return await ctx.db.insert("overwatchSessions", {
      blindUserProfileId: blindUser._id,
      guardianProfileId: blindUser.guardianProfileId,
      livekitRoomName: args.livekitRoomName,
      status: "active",
      startedAt: Date.now(),
    });
  },
});

// End an overwatch session
export const endSession = mutation({
  args: { sessionId: v.id("overwatchSessions") },
  returns: v.null(),
  handler: async (ctx, args) => {
    const profile = await getMyProfile(ctx);
    const session = await ctx.db.get(args.sessionId);
    if (!session) {
      throw new ConvexError("Session not found");
    }

    // Only the blind user or their guardian can end the session
    const isBlindUser = session.blindUserProfileId === profile._id;
    const isGuardian = session.guardianProfileId === profile._id;
    if (!(isBlindUser || isGuardian)) {
      throw new ConvexError("Not authorized to end this session");
    }

    await ctx.db.patch(args.sessionId, {
      status: "ended",
      endedAt: Date.now(),
    });
    return null;
  },
});
