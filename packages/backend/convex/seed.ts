import { v } from "convex/values";
import { internal } from "./_generated/api";
import type { Id } from "./_generated/dataModel";
import { action } from "./_generated/server";

/**
 * One-off seed for the public crowdsourced hazard map.
 *
 * Inserts 5 hazardReports around the /map DEFAULT_CENTER, each within ~200m,
 * each backed by a real photo (fetched from the provided news URLs and stored
 * in Convex File Storage so listReports can mint a signed imageUrl).
 *
 * Idempotent: re-running clears the previous seed reports first.
 */

// DEFAULT_CENTER from apps/web/src/app/map/hazard-map.tsx [lng, lat].
const CENTER_LNG = 106.618_691_395_682_96;
const CENTER_LAT = -6.257_145_712_100_773;

interface ImageSpec {
  bearingDeg: number;
  description: string;
  // offset from CENTER, in meters, with bearing in degrees (0 = north).
  distanceMeters: number;
  locationDescription: string;
  url: string;
}

const IMAGES: ImageSpec[] = [
  {
    url: "https://asset.kompas.com/crops/J9we3rxfd5ZAemXjflw9VvE-0NQ=/0x0:0x0/1200x800/data/photo/2026/01/27/69788483058a8.jpg",
    distanceMeters: 40,
    bearingDeg: 30,
    locationDescription:
      "Trotoar Jalan Gunung Sahari 1, sebelah utara perempatan",
    description:
      "Trotoar retak dan berlubang lebar, ubin terangkat akibat akar pohon. Bahaya bagi pengguna kruk dan kursi roda.",
  },
  {
    url: "https://asset.kompas.com/crops/u5llOhCAV2-lyYtxoxFmhhC6dKo=/0x0:0x0/1200x800/data/photo/2026/01/20/696fb0038fc00.jpeg",
    distanceMeters: 90,
    bearingDeg: 110,
    locationDescription: "Badan jalan dekat halte TransJakarta, Cempaka Putih",
    description:
      "Lubang cukup dalam di badan jalan, berisi air setelah hujan. Mobil dan motor berusaha menghindari.",
  },
  {
    url: "https://awsimages.detik.net.id/community/media/visual/2023/07/26/kondisi-trotoar-di-kawasan-lovina-yang-berlubang-selasa-2572023-made-wijaya-kusuma.jpeg?w=500&q=90",
    distanceMeters: 130,
    bearingDeg: 200,
    locationDescription: "Trotoar sepanjang Jalan Kemuning Raya",
    description:
      "Trotoar berlubang dan paving copot sepanjang ~10 meter. Pejalan kaki terpaksa turun ke badan jalan.",
  },
  {
    url: "https://static.republika.co.id/uploads/images/inpicture_slide/190515154031-178.jpg",
    distanceMeters: 70,
    bearingDeg: 290,
    locationDescription: "Persimpangan Jalan Anggrek, sudut barat daya",
    description:
      "Trotoar rusak parah, paving terangkat dan tidak rata. Penyandang disabilitas visual berisiko tersandung.",
  },
  {
    url: "https://blue.kumparan.com/image/upload/fl_progressive,fl_lossy,c_fill,f_auto,q_auto:best,w_640/v1634025439/01jwd15yvr4hjv0x631tr3qy60.jpg",
    distanceMeters: 170,
    bearingDeg: 60,
    locationDescription: "Saluran air terbuka pinggir Jalan Melati",
    description:
      "Saluran air terbuka tanpa tutup di pinggir trotoar. Berisiko jatuh bagi pejalan kaki, terutama tunanetra.",
  },
];

// Convert a distance + bearing (from CENTER) into a [lat, lng] offset, then
// add to the center. Uses the equirectangular approximation — accurate enough
// at the sub-200m scale of this seed.
function offsetLatlng(
  lat: number,
  lng: number,
  distanceMeters: number,
  bearingDeg: number
): { latitude: number; longitude: number } {
  const bearing = (bearingDeg * Math.PI) / 180;
  const metersPerDegLat = 111_320;
  const metersPerDegLng = 111_320 * Math.cos((lat * Math.PI) / 180);
  const dLat = (distanceMeters * Math.cos(bearing)) / metersPerDegLat;
  const dLng = (distanceMeters * Math.sin(bearing)) / metersPerDegLng;
  return { latitude: lat + dLat, longitude: lng + dLng };
}

// --- Public action: fetch + store images, then hand off to the DB mutation. ---
export const seedHazardReports = action({
  args: {},
  returns: v.array(v.id("hazardReports")),
  handler: async (ctx): Promise<Id<"hazardReports">[]> => {
    const reports: {
      latitude: number;
      longitude: number;
      locationDescription: string;
      description: string;
      imageStorageId: Id<"_storage"> | null;
    }[] = [];

    for (const spec of IMAGES) {
      const { latitude, longitude } = offsetLatlng(
        CENTER_LAT,
        CENTER_LNG,
        spec.distanceMeters,
        spec.bearingDeg
      );

      let imageStorageId: Id<"_storage"> | null = null;
      try {
        const res = await fetch(spec.url, { method: "GET" });
        if (res.ok) {
          const blob = await res.blob();
          imageStorageId = await ctx.storage.store(blob);
        }
      } catch {
        // Non-fatal: seed the report without an image if the fetch fails.
        imageStorageId = null;
      }

      reports.push({
        latitude,
        longitude,
        locationDescription: spec.locationDescription,
        description: spec.description,
        imageStorageId,
      });
    }

    return await ctx.runMutation(internal.seedInternal.runSeed, { reports });
  },
});
