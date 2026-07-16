import { ConvexError, v } from "convex/values";
import { mutation, query } from "./_generated/server";
import { authComponent } from "./auth";

export const create = mutation({
  args: {
    role: v.union(v.literal("blind_user"), v.literal("guardian")),
    fullName: v.string(),
    whatsappNumber: v.optional(v.string()),
  },
  returns: v.id("userProfiles"),
  handler: async (ctx, args) => {
    const authUser = await authComponent.safeGetAuthUser(ctx);
    if (!authUser) {
      throw new ConvexError("Not authenticated");
    }

    // Idempotent: return existing profile if already created
    const existing = await ctx.db
      .query("userProfiles")
      .withIndex("by_authUserId", (q) => q.eq("authUserId", authUser._id))
      .first();
    if (existing) {
      return existing._id;
    }

    // Guardian must provide WhatsApp number for Overwatch link
    if (args.role === "guardian" && !args.whatsappNumber) {
      throw new ConvexError("WhatsApp number is required for guardians");
    }

    return await ctx.db.insert("userProfiles", {
      authUserId: authUser._id,
      email: authUser.email,
      role: args.role,
      fullName: args.fullName,
      whatsappNumber: args.whatsappNumber,
    });
  },
});

export const update = mutation({
  args: {
    fullName: v.optional(v.string()),
    whatsappNumber: v.optional(v.string()),
  },
  returns: v.null(),
  handler: async (ctx, args) => {
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

    const patch: Partial<typeof profile> = {};
    if (args.fullName !== undefined) {
      patch.fullName = args.fullName;
    }
    if (args.whatsappNumber !== undefined) {
      // Guardian must always have a WhatsApp number
      if (profile.role === "guardian" && !args.whatsappNumber) {
        throw new ConvexError("WhatsApp number is required for guardians");
      }
      patch.whatsappNumber = args.whatsappNumber;
    }

    await ctx.db.patch(profile._id, patch);
    return null;
  },
});

export const getCurrent = query({
  args: {},
  returns: v.union(
    v.object({
      _id: v.id("userProfiles"),
      _creationTime: v.number(),
      authUserId: v.string(),
      email: v.optional(v.string()),
      role: v.union(v.literal("blind_user"), v.literal("guardian")),
      fullName: v.string(),
      whatsappNumber: v.optional(v.string()),
      guardianProfileId: v.optional(v.id("userProfiles")),
    }),
    v.null()
  ),
  handler: async (ctx) => {
    const authUser = await authComponent.safeGetAuthUser(ctx);
    if (!authUser) {
      return null;
    }

    return await ctx.db
      .query("userProfiles")
      .withIndex("by_authUserId", (q) => q.eq("authUserId", authUser._id))
      .first();
  },
});
