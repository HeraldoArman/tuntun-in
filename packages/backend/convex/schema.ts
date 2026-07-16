import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

/**
 * Tuntun.In — Convex Schema (hackathon-lean version)
 *
 * 4 core tables only, matching the 4 features actually being demoed:
 * profiles, crowdsourced hazard map, navigation session, overwatch (SOS).
 *
 * - Auth is Better Auth (separate component, its own users table), so we
 *   just store its user id as a string (`authUserId`) and index on it.
 * - Guardian relation is 1-on-1: a blind_user profile optionally points to
 *   one guardian profile. No separate join table.
 * - Hazard photos go to Convex File Storage (`imageStorageId`).
 * - No event-log tables (navigationEvents / transitScanEvents) — those are
 *   nice-to-have analytics, not needed for the demo. Add later if needed.
 */

export default defineSchema({
  userProfiles: defineTable({
    authUserId: v.string(), // Better Auth user id
    email: v.optional(v.string()), // denormalized from Better Auth for lookups
    role: v.union(v.literal("blind_user"), v.literal("guardian")),
    fullName: v.string(),
    whatsappNumber: v.optional(v.string()), // used for Overwatch link

    // Only set when role === "blind_user". 1-on-1 guardian link.
    guardianProfileId: v.optional(v.id("userProfiles")),
  })
    .index("by_authUserId", ["authUserId"])
    .index("by_email", ["email"]),

  // Guardian ↔ Blind User link (a guardian can watch multiple blind users)
  guardianLinks: defineTable({
    guardianProfileId: v.id("userProfiles"),
    blindUserProfileId: v.id("userProfiles"),
    createdAt: v.number(),
  })
    .index("by_guardianProfileId", ["guardianProfileId"])
    .index("by_blindUserProfileId", ["blindUserProfileId"]),

  // Live Crowdsourced Mapping
  hazardReports: defineTable({
    reporterProfileId: v.id("userProfiles"),

    latitude: v.number(),
    longitude: v.number(),
    // Written by the AI agent (has Google Maps access) — road names,
    // nearby landmarks, etc. Free text instead of a fixed enum.
    locationDescription: v.string(),

    description: v.optional(v.string()),
    imageStorageId: v.optional(v.id("_storage")),

    status: v.union(v.literal("pending_review"), v.literal("verified")),
    detectedAt: v.number(),
  }).index("by_status", ["status"]),

  // Deep Navigator
  navigationSessions: defineTable({
    blindUserProfileId: v.id("userProfiles"),

    originLat: v.number(),
    originLng: v.number(),
    destinationLat: v.number(),
    destinationLng: v.number(),
    destinationLabel: v.optional(v.string()),

    status: v.union(v.literal("active"), v.literal("completed")),
    startedAt: v.number(),
    endedAt: v.optional(v.number()),
  }).index("by_blindUserProfileId", ["blindUserProfileId"]),

  // Overwatch Mode
  overwatchSessions: defineTable({
    blindUserProfileId: v.id("userProfiles"),
    guardianProfileId: v.optional(v.id("userProfiles")),

    livekitRoomName: v.string(),
    status: v.union(v.literal("active"), v.literal("ended")),

    startedAt: v.number(),
    endedAt: v.optional(v.number()),
  })
    .index("by_blindUserProfileId", ["blindUserProfileId"])
    .index("by_guardianProfileId", ["guardianProfileId"]),
});
