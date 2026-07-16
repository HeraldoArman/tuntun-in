import { v } from "convex/values";
import { mutation } from "./_generated/server";

/**
 * Live Crowdsourced Mapping — agent mutations.
 *
 * Called by the Python LiveKit worker (Reflex agent) when it spots damaged
 * road/sidewalk on the chest camera. Protected by CONVEX_SERVICE_SECRET, NOT
 * user auth (the agent has no user session).
 *
 * Flow (agent side):
 *   1. agent captures the latest camera frame -> JPEG bytes
 *   2. agent calls generateUploadUrl -> presigned URL
 *   3. agent POSTs the JPEG bytes -> { storageId }
 *   4. agent calls ingestReport with the storageId + GPS + description ->
 *      a hazardReports row is created (status "pending_review")
 *
 * This is SILENT crowdsourced mapping — the blind user is never prompted. The
 * agent just logs the hazard for the public dashboard.
 */

function assertSecret(secret: string) {
  const expected = process.env.CONVEX_SERVICE_SECRET;
  if (!expected || secret !== expected) {
    throw new Error("unauthorized");
  }
}

// Generate a short-lived upload URL for the agent to POST a JPEG snapshot to.
export const generateUploadUrl = mutation({
  args: { secret: v.string() },
  returns: v.string(),
  handler: async (ctx, args) => {
    assertSecret(args.secret);
    return await ctx.storage.generateUploadUrl();
  },
});

// Persist a crowdsourced hazard report. The image is already in Convex file
// storage (the agent uploaded it via generateUploadUrl); we only store its id.
export const ingestReport = mutation({
  args: {
    secret: v.string(),
    reporterProfileId: v.id("userProfiles"),
    latitude: v.number(),
    longitude: v.number(),
    locationDescription: v.string(),
    description: v.optional(v.string()),
    imageStorageId: v.optional(v.id("_storage")),
  },
  returns: v.id("hazardReports"),
  handler: async (ctx, args) => {
    assertSecret(args.secret);

    const reporter = await ctx.db.get(args.reporterProfileId);
    if (!reporter) {
      throw new Error("reporter profile not found");
    }

    return await ctx.db.insert("hazardReports", {
      reporterProfileId: reporter._id,
      latitude: args.latitude,
      longitude: args.longitude,
      locationDescription: args.locationDescription,
      description: args.description,
      imageStorageId: args.imageStorageId,
      status: "pending_review",
      detectedAt: Date.now(),
    });
  },
});
