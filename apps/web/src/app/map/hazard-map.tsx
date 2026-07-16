"use client";

import "./map.css";

import { api } from "@tuntun-in/backend/convex/_generated/api";
import { cn } from "@tuntun-in/ui/lib/utils";
import { useQuery } from "convex/react";
import { Clock, MapPin, ShieldAlertIcon } from "lucide-react";
import Image from "next/image";
import { type RefObject, useMemo, useRef } from "react";

import {
  MapControls,
  MapMarker,
  Map as MapView,
  MarkerContent,
  MarkerPopup,
  MarkerTooltip,
} from "@/components/ui/map";

// Default (lng, lat — MapLibre order) when no reports exist yet.
const DEFAULT_CENTER: [number, number] = [
  106.618_691_395_682_96, -6.257_145_712_100_773,
];
const DEFAULT_ZOOM = 15;

interface HazardReport {
  _id: string;
  description?: string;
  detectedAt: number;
  imageUrl: string | null;
  latitude: number;
  locationDescription: string;
  longitude: number;
  reporterFullName: string;
  status: "pending_review" | "verified";
}

interface MarkerHandle {
  openPopup: () => void;
}

const formatDate = (ms: number) =>
  new Date(ms).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });

function statusStyles(status: HazardReport["status"]) {
  return status === "verified"
    ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
    : "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400";
}

function statusLabel(status: HazardReport["status"]) {
  return status === "verified" ? "Verified" : "Pending review";
}

function dotColor(status: HazardReport["status"]) {
  return status === "verified" ? "bg-emerald-500" : "bg-rose-500";
}

/** Sidebar body — empty state vs the list of report cards (early return). */
function ReportCards({
  list,
  markerRefs,
}: {
  list: HazardReport[];
  markerRefs: RefObject<Record<string, MarkerHandle>>;
}) {
  if (list.length === 0) {
    return (
      <div className="rounded-xl border border-dashed p-6 text-center">
        <ShieldAlertIcon className="mx-auto mb-2 size-6 text-muted-foreground" />
        <p className="text-muted-foreground text-sm">
          No hazards reported yet. They appear here automatically as Tuntun
          users walk past damaged roads and sidewalks.
        </p>
      </div>
    );
  }

  return list.map((report) => (
    <button
      className="group w-full overflow-hidden rounded-xl border bg-card text-left transition-colors hover:border-foreground/20"
      key={report._id}
      onClick={() => markerRefs.current[report._id]?.openPopup()}
      type="button"
    >
      {report.imageUrl ? (
        <div className="relative h-28 w-full overflow-hidden">
          <Image
            alt={report.locationDescription}
            className="object-cover transition-transform group-hover:scale-105"
            fill
            sizes="20rem"
            src={report.imageUrl}
            unoptimized
          />
        </div>
      ) : null}
      <div className="space-y-2 p-3">
        <div className="flex items-center justify-between gap-2">
          <span
            className={cn(
              "inline-flex items-center rounded-full border px-2 py-0.5 text-xs",
              statusStyles(report.status)
            )}
          >
            {statusLabel(report.status)}
          </span>
          <span className="flex items-center gap-1 text-muted-foreground text-xs">
            <Clock className="size-3" />
            {formatDate(report.detectedAt)}
          </span>
        </div>
        <p className="line-clamp-2 font-medium text-sm">
          {report.description || report.locationDescription}
        </p>
        <p className="flex items-start gap-1 text-muted-foreground text-xs">
          <MapPin className="mt-0.5 size-3 shrink-0" />
          <span className="line-clamp-1">{report.locationDescription}</span>
        </p>
        <p className="font-mono text-[11px] text-muted-foreground/80">
          {report.latitude.toFixed(5)}, {report.longitude.toFixed(5)}
        </p>
      </div>
    </button>
  ));
}

/**
 * Public crowdsourced hazard map. Reads hazardReports (written silently by the
 * Reflex agent) and plots them on an interactive MapLibre map with a clickable
 * sidebar list. Clicking a card opens the matching marker popup.
 */
export function HazardMap() {
  const reports = useQuery(api.hazard.listReports);
  const markerRefs = useRef<Record<string, MarkerHandle>>({});

  const list = (reports ?? []) as HazardReport[];
  const loading = reports === undefined;

  const center: [number, number] = useMemo(() => {
    if (list.length > 0) {
      return [list[0].longitude, list[0].latitude];
    }
    return DEFAULT_CENTER;
  }, [list]);

  return (
    <div className="flex min-h-[70vh] flex-col gap-4 lg:flex-row">
      {/* Sidebar — report list */}
      <aside className="flex w-full shrink-0 flex-col gap-3 lg:w-96">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-lg tracking-tight">
            Reported hazards
          </h2>
          <span className="rounded-full border bg-muted px-2.5 py-0.5 text-muted-foreground text-xs">
            {loading ? "…" : list.length}
          </span>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto pr-1 lg:max-h-[70vh]">
          {loading ? (
            <p className="text-muted-foreground text-sm">Loading reports…</p>
          ) : (
            <ReportCards list={list} markerRefs={markerRefs} />
          )}
        </div>
      </aside>

      {/* Map */}
      <div className="relative min-h-[50vh] flex-1 overflow-hidden rounded-2xl border">
        <MapView center={center} zoom={DEFAULT_ZOOM}>
          <MapControls />
          {list.map((report) => (
            <MapMarker
              key={report._id}
              latitude={report.latitude}
              longitude={report.longitude}
              ref={(ref) => {
                if (ref) {
                  markerRefs.current[report._id] = ref;
                }
              }}
            >
              <MarkerContent>
                <div
                  className={cn(
                    "size-4 cursor-pointer rounded-full border-2 border-white shadow-lg transition-transform hover:scale-125",
                    dotColor(report.status)
                  )}
                />
              </MarkerContent>
              <MarkerTooltip>{report.locationDescription}</MarkerTooltip>
              <MarkerPopup className="w-64 p-0">
                {report.imageUrl ? (
                  <div className="relative h-32 w-full overflow-hidden rounded-t-md">
                    <Image
                      alt={report.locationDescription}
                      className="object-cover"
                      fill
                      sizes="16rem"
                      src={report.imageUrl}
                      unoptimized
                    />
                  </div>
                ) : null}
                <div className="space-y-2 p-3">
                  <span
                    className={cn(
                      "inline-flex items-center rounded-full border px-2 py-0.5 text-xs",
                      statusStyles(report.status)
                    )}
                  >
                    {statusLabel(report.status)}
                  </span>
                  <p className="font-medium text-sm leading-tight">
                    {report.description || report.locationDescription}
                  </p>
                  <p className="flex items-start gap-1 text-muted-foreground text-xs">
                    <MapPin className="mt-0.5 size-3 shrink-0" />
                    {report.locationDescription}
                  </p>
                  <p className="font-mono text-[11px] text-muted-foreground/80">
                    {report.latitude.toFixed(5)}, {report.longitude.toFixed(5)}
                  </p>
                  <p className="flex items-center justify-between text-[11px] text-muted-foreground">
                    <span>by {report.reporterFullName}</span>
                    <span className="flex items-center gap-1">
                      <Clock className="size-3" />
                      {formatDate(report.detectedAt)}
                    </span>
                  </p>
                </div>
              </MarkerPopup>
            </MapMarker>
          ))}
        </MapView>
      </div>
    </div>
  );
}

export default HazardMap;
