"use client";

import { usePreloadedAuthQuery } from "@convex-dev/better-auth/nextjs/client";
import type { api } from "@tuntun-in/backend/convex/_generated/api";
import type { Preloaded } from "convex/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { PageLoader } from "@/components/page-loader";

export function DashboardView({
  preloadedUser,
  preloadedProfile,
}: {
  preloadedUser: Preloaded<typeof api.auth.getCurrentUser>;
  preloadedProfile: Preloaded<typeof api.userProfiles.getCurrent>;
}) {
  const router = useRouter();
  const user = usePreloadedAuthQuery(preloadedUser);
  const profile = usePreloadedAuthQuery(preloadedProfile);

  useEffect(() => {
    if (user === null) {
      router.replace("/login" as never);
    }
  }, [user, router]);

  useEffect(() => {
    if (profile !== undefined && profile === null) {
      router.replace("/onboarding" as never);
    }
  }, [profile, router]);

  if (user === null || profile === null) {
    return <PageLoader />;
  }

  if (user === undefined || profile === undefined) {
    return <PageLoader />;
  }

  return (
    <div className="p-6">
      <h1>Dashboard</h1>
      <p>Welcome, {profile.fullName}</p>
    </div>
  );
}
