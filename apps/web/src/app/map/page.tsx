import { MapIcon } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { HazardMap } from "./hazard-map";

/**
 * Live Crowdsourced Mapping — public dashboard.
 *
 * Anyone can view this page (no auth). It plots hazard reports that the Reflex
 * agent silently files while blind users walk past damaged roads and sidewalks.
 * The data itself is loaded client-side via Convex realtime (see HazardMap).
 */
export default function MapPage() {
  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-30 border-b bg-background/80 backdrop-blur-lg">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
          <Link
            aria-label="Tuntun.In home"
            className="flex items-center gap-2"
            href="/"
          >
            <Image
              alt="Tuntun.In"
              className="h-7 w-auto"
              height={28}
              priority
              src="/logo/logo.png"
              width={138}
            />
          </Link>
          <div className="flex items-center gap-3">
            <span className="hidden items-center gap-1.5 rounded-full border bg-muted px-3 py-1 text-muted-foreground text-xs sm:inline-flex">
              <span className="relative flex size-2">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-500/60" />
                <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
              </span>
              Live crowdsourced feed
            </span>
            <Link
              className="text-muted-foreground text-sm transition-colors hover:text-foreground"
              href="/"
            >
              Back to home
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-6 flex items-start gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-xl border bg-muted">
            <MapIcon className="size-5 text-foreground" />
          </div>
          <div>
            <h1 className="font-semibold text-2xl tracking-tight">
              Live Crowdsourced Hazard Map
            </h1>
            <p className="mt-1 max-w-2xl text-balance text-muted-foreground text-sm">
              Damaged roads and sidewalks detected by Tuntun.In users, mapped
              automatically and silently as they walk. No manual reporting — the
              AI captures the scene, the coordinates, and a description for each
              hazard so the whole community can avoid them.
            </p>
          </div>
        </div>

        <HazardMap />
      </main>
    </div>
  );
}
