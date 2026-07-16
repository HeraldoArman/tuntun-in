import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

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

// Haversine distance in meters between two lat/lng points.
function haversineMeters(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number
): number {
  const R = 6_371_000; // Earth radius in meters
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

// List crowdsourced hazards within `radiusMeters` of a point. Used by the
// Reasoning Layer (Deep Navigator detour) to avoid known bad road/sidewalk.
// ponytail: full-table scan + haversine filter — no geo index on hazardReports
// (only by_status). Fine while the table is small; add a Convex geo index only
// if the report count grows past a scan.
export const listNearby = query({
  args: {
    secret: v.string(),
    latitude: v.number(),
    longitude: v.number(),
    radiusMeters: v.optional(v.number()),
  },
  returns: v.array(
    v.object({
      _id: v.id("hazardReports"),
      latitude: v.number(),
      longitude: v.number(),
      locationDescription: v.string(),
      description: v.optional(v.string()),
      status: v.union(v.literal("pending_review"), v.literal("verified")),
      detectedAt: v.number(),
      distanceMeters: v.number(),
    })
  ),
  handler: async (ctx, args) => {
    assertSecret(args.secret);
    const radius = args.radiusMeters ?? 150;
    const all = await ctx.db.query("hazardReports").collect();
    return all
      .map((r) => ({
        _id: r._id,
        latitude: r.latitude,
        longitude: r.longitude,
        locationDescription: r.locationDescription,
        description: r.description,
        status: r.status,
        detectedAt: r.detectedAt,
        distanceMeters: haversineMeters(
          args.latitude,
          args.longitude,
          r.latitude,
          r.longitude
        ),
      }))
      .filter((r) => r.distanceMeters <= radius)
      .sort((a, b) => a.distanceMeters - b.distanceMeters);
  },
});
