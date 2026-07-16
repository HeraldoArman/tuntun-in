import { v } from "convex/values";
import { internalMutation } from "./_generated/server";

// Seed reporter identity (kept here in sync with seed.ts).
const SEED_AUTH_USER_ID = "seed-agent-profile";
const SEED_FULL_NAME = "Tuntun Seed Agent";

/**
 * Internal mutation: write the seed profile + reports idempotently.
 *
 * Split into its own module so the public action in seed.ts can reference it
 * via internal.seedInternal.runSeed without creating a self-referential type
 * cycle within the `seed` module.
 */
export const runSeed = internalMutation({
  args: {
    reports: v.array(
      v.object({
        latitude: v.number(),
        longitude: v.number(),
        locationDescription: v.string(),
        description: v.string(),
        imageStorageId: v.union(v.id("_storage"), v.null()),
      })
    ),
  },
  returns: v.array(v.id("hazardReports")),
  handler: async (ctx, args) => {
    // Find or create the seed reporter profile.
    let reporter = await ctx.db
      .query("userProfiles")
      .withIndex("by_authUserId", (q) => q.eq("authUserId", SEED_AUTH_USER_ID))
      .first();

    if (!reporter) {
      const id = await ctx.db.insert("userProfiles", {
        authUserId: SEED_AUTH_USER_ID,
        role: "blind_user",
        fullName: SEED_FULL_NAME,
      });
      reporter = await ctx.db.get(id);
    }
    if (!reporter) {
      throw new Error("failed to create seed reporter profile");
    }

    // Idempotency: delete prior seed reports by this reporter before re-inserting.
    // by_status indexes both statuses; sweep both to fully clear prior seed rows.
    for (const status of ["pending_review", "verified"] as const) {
      const existing = await ctx.db
        .query("hazardReports")
        .withIndex("by_status", (q) => q.eq("status", status))
        .collect();
      for (const r of existing) {
        if (r.reporterProfileId === reporter._id) {
          // Best-effort: also drop the stored image so we don't leak storage.
          if (r.imageStorageId) {
            await ctx.storage.delete(r.imageStorageId);
          }
          await ctx.db.delete(r._id);
        }
      }
    }

    const now = Date.now();
    const ids = await Promise.all(
      args.reports.map(async (report, i) => {
        return await ctx.db.insert("hazardReports", {
          reporterProfileId: reporter._id,
          latitude: report.latitude,
          longitude: report.longitude,
          locationDescription: report.locationDescription,
          description: report.description,
          imageStorageId: report.imageStorageId ?? undefined,
          status: "pending_review",
          // Stagger detectedAt so the "newest first" ordering is visible on the map.
          detectedAt: now - i * 60_000,
        });
      })
    );
    return ids;
  },
});
