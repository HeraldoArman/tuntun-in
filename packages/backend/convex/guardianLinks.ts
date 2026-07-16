import { ConvexError, v } from "convex/values";
import type { MutationCtx, QueryCtx } from "./_generated/server";
import { mutation, query } from "./_generated/server";
import { authComponent } from "./auth";

/**
 * Guardian ↔ Blind User link management.
 *
 * A guardian can watch multiple blind users. A blind user can have multiple
 * guardians (e.g. both parents). The link is created by the guardian by
 * looking up the blind user's profile by email.
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

export const addBlindUser = mutation({
  args: { blindUserEmail: v.string() },
  returns: v.id("guardianLinks"),
  handler: async (ctx, args) => {
    const guardian = await getMyProfile(ctx);
    if (guardian.role !== "guardian") {
      throw new ConvexError("Only guardians can add blind users");
    }

    const normalizedEmail = args.blindUserEmail.trim().toLowerCase();
    if (!normalizedEmail) {
      throw new ConvexError("Email is required");
    }

    const blindUser = await ctx.db
      .query("userProfiles")
      .withIndex("by_email", (q) => q.eq("email", normalizedEmail))
      .first();

    if (!blindUser) {
      throw new ConvexError(
        "No user found with that email. Ask them to register and complete onboarding first."
      );
    }
    if (blindUser.role !== "blind_user") {
      throw new ConvexError("That user is a guardian, not a blind user");
    }
    if (blindUser._id === guardian._id) {
      throw new ConvexError("You cannot add yourself");
    }

    const existing = await ctx.db
      .query("guardianLinks")
      .withIndex("by_guardianProfileId", (q) =>
        q.eq("guardianProfileId", guardian._id)
      )
      .collect();
    if (existing.some((l) => l.blindUserProfileId === blindUser._id)) {
      throw new ConvexError("You are already linked to this user");
    }

    const linkId = await ctx.db.insert("guardianLinks", {
      guardianProfileId: guardian._id,
      blindUserProfileId: blindUser._id,
      createdAt: Date.now(),
    });

    if (!blindUser.guardianProfileId) {
      await ctx.db.patch(blindUser._id, {
        guardianProfileId: guardian._id,
      });
    }

    return linkId;
  },
});
export const removeBlindUser = mutation({
  args: { blindUserProfileId: v.id("userProfiles") },
  returns: v.null(),
  handler: async (ctx, args) => {
    const guardian = await getMyProfile(ctx);
    if (guardian.role !== "guardian") {
      throw new ConvexError("Only guardians can remove blind users");
    }

    const links = await ctx.db
      .query("guardianLinks")
      .withIndex("by_guardianProfileId", (q) =>
        q.eq("guardianProfileId", guardian._id)
      )
      .collect();
    const link = links.find(
      (l) => l.blindUserProfileId === args.blindUserProfileId
    );

    if (!link) {
      throw new ConvexError("Link not found");
    }

    await ctx.db.delete(link._id);

    const blindUser = await ctx.db.get(args.blindUserProfileId);
    if (blindUser?.guardianProfileId === guardian._id) {
      const otherLinks = await ctx.db
        .query("guardianLinks")
        .withIndex("by_blindUserProfileId", (q) =>
          q.eq("blindUserProfileId", args.blindUserProfileId)
        )
        .first();
      await ctx.db.patch(args.blindUserProfileId, {
        guardianProfileId: otherLinks?.guardianProfileId,
      });
    }

    return null;
  },
});

export const getMyBlindUsers = query({
  args: {},
  returns: v.array(
    v.object({
      _id: v.id("userProfiles"),
      fullName: v.string(),
      email: v.optional(v.string()),
      guardianProfileId: v.optional(v.id("userProfiles")),
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

    const blindUsers = await Promise.all(
      links.map(async (link) => {
        const profile = await ctx.db.get(link.blindUserProfileId);
        if (!profile) {
          return null;
        }
        return {
          _id: profile._id,
          fullName: profile.fullName,
          email: profile.email,
          guardianProfileId: profile.guardianProfileId,
        };
      })
    );

    return blindUsers.filter((u): u is NonNullable<typeof u> => u !== null);
  },
});

export const getMyGuardians = query({
  args: {},
  returns: v.array(
    v.object({
      _id: v.id("userProfiles"),
      fullName: v.string(),
      email: v.optional(v.string()),
      whatsappNumber: v.optional(v.string()),
    })
  ),
  handler: async (ctx) => {
    const blindUser = await getMyProfile(ctx);
    if (blindUser.role !== "blind_user") {
      return [];
    }

    const links = await ctx.db
      .query("guardianLinks")
      .withIndex("by_blindUserProfileId", (q) =>
        q.eq("blindUserProfileId", blindUser._id)
      )
      .collect();

    const guardians = await Promise.all(
      links.map(async (link) => {
        const profile = await ctx.db.get(link.guardianProfileId);
        if (!profile) {
          return null;
        }
        return {
          _id: profile._id,
          fullName: profile.fullName,
          email: profile.email,
          whatsappNumber: profile.whatsappNumber,
        };
      })
    );

    return guardians.filter((g): g is NonNullable<typeof g> => g !== null);
  },
});
