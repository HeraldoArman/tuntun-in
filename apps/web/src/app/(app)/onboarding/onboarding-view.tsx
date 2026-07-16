"use client";

import { usePreloadedAuthQuery } from "@convex-dev/better-auth/nextjs/client";
import type { api } from "@tuntun-in/backend/convex/_generated/api";
import type { Preloaded } from "convex/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { PageLoader } from "@/components/page-loader";
import { OnboardingForm } from "@/modules/auth/onboarding-form";

export function OnboardingView({
  preloadedUser,
}: {
  preloadedUser: Preloaded<typeof api.auth.getCurrentUser>;
}) {
  const router = useRouter();
  const user = usePreloadedAuthQuery(preloadedUser);

  useEffect(() => {
    if (user === null) {
      router.replace("/login" as never);
    }
  }, [user, router]);

  if (user === null) {
    return (
      <PageLoader description="Taking you to login..." title="Redirecting" />
    );
  }

  if (user === undefined) {
    return <PageLoader />;
  }

  return (
    <section className="flex min-h-screen bg-muted/30 px-4 py-16 md:py-32">
      <OnboardingForm authName={user.name} />
    </section>
  );
}
