import { v } from "convex/values";
import { query } from "./_generated/server";

/**
 * Live Crowdsourced Mapping — public read API.
 *
 * The Reflex agent silently writes hazardReports rows (see hazardAgent.ts)
 * whenever it sees damaged road/sidewalk on the chest camera. This module
 * exposes the public, read-only dashboard query that powers /map — the public
 * crowdsourced hazard map. No auth: anyone can view reported hazards.
 */

// List the most recent hazard reports for the public map dashboard. Each report
// carries a signed imageUrl (from Convex file storage) so the dashboard can
// render the snapshot the agent captured. Newest first, capped at 200 so the
// map stays readable.
export const listReports = query({
  args: {},
  returns: v.array(
    v.object({
      _id: v.id("hazardReports"),
      latitude: v.number(),
      longitude: v.number(),
      locationDescription: v.string(),
      description: v.optional(v.string()),
      imageUrl: v.union(v.string(), v.null()),
      status: v.union(v.literal("pending_review"), v.literal("verified")),
      detectedAt: v.number(),
      reporterFullName: v.string(),
    })
  ),
  handler: async (ctx) => {
    const reports = await ctx.db.query("hazardReports").order("desc").take(200);

    return Promise.all(
      reports.map(async (r) => {
        const reporter = await ctx.db.get(r.reporterProfileId);
        const imageUrl = r.imageStorageId
          ? await ctx.storage.getUrl(r.imageStorageId)
          : null;
        return {
          _id: r._id,
          latitude: r.latitude,
          longitude: r.longitude,
          locationDescription: r.locationDescription,
          description: r.description,
          imageUrl,
          status: r.status,
          detectedAt: r.detectedAt,
          reporterFullName: reporter?.fullName ?? "Anonymous",
        };
      })
    );
  },
});
