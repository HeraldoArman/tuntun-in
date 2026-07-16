"use client";

import { usePreloadedAuthQuery } from "@convex-dev/better-auth/nextjs/client";
import { api } from "@tuntun-in/backend/convex/_generated/api";
import { Badge } from "@tuntun-in/ui/components/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@tuntun-in/ui/components/card";
import type { Preloaded } from "convex/react";
import { useQuery } from "convex/react";
import { EyeIcon, ShieldIcon, UsersIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { PageLoader } from "@/components/page-loader";

function renderList<T>(
  data: T[] | undefined,
  renderItem: (item: T) => React.ReactNode,
  emptyMessage: string
) {
  if (data === undefined) {
    return <p className="text-muted-foreground text-sm">Loading...</p>;
  }
  if (data.length === 0) {
    return <p className="text-muted-foreground text-sm">{emptyMessage}</p>;
  }
  return (
    <ul className="flex flex-col gap-3">
      {data.map((item, index) => (
        <li key={index}>{renderItem(item)}</li>
      ))}
    </ul>
  );
}

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

  const blindUsers = useQuery(api.guardianLinks.getMyBlindUsers);
  const guardians = useQuery(api.guardianLinks.getMyGuardians);
  const activeOverwatch = useQuery(api.overwatch.getActiveForGuardian);

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

  const isGuardian = profile.role === "guardian";

  if (!isGuardian) {
    return (
      <div className="p-6">
        <div className="mb-8">
          <h1 className="font-semibold text-2xl">
            Welcome, {profile.fullName}
          </h1>
          <p className="mt-1 text-muted-foreground text-sm">
            Your safety companion is ready.
          </p>
        </div>
        <div className="flex max-w-2xl flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <ShieldIcon className="size-5" />
                Your Guardians
              </CardTitle>
            </CardHeader>
            <CardContent>
              {renderList(
                guardians,
                (guardian) => (
                  <div className="flex items-center justify-between rounded-lg border p-3">
                    <div className="flex flex-col gap-0.5">
                      <span className="font-medium text-sm">
                        {guardian.fullName}
                      </span>
                      {guardian.email && (
                        <span className="text-muted-foreground text-xs">
                          {guardian.email}
                        </span>
                      )}
                    </div>
                    <Badge variant="default">Guardian</Badge>
                  </div>
                ),
                "No guardian linked yet. Ask a family member to register as a guardian and add you by email."
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="mb-8">
        <h1 className="font-semibold text-2xl">Welcome, {profile.fullName}</h1>
        <p className="mt-1 text-muted-foreground text-sm">
          Monitor your linked blind users and respond to Overwatch alerts.
        </p>
      </div>

      <div className="flex flex-col gap-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="font-medium text-sm">
                Linked Blind Users
              </CardTitle>
              <UsersIcon className="size-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="font-bold text-2xl">
                {blindUsers?.length ?? "—"}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="font-medium text-sm">
                Active Overwatch Alerts
              </CardTitle>
              <EyeIcon className="size-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="font-bold text-2xl">
                {activeOverwatch?.length ?? "—"}
              </div>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <ShieldIcon className="size-5" />
              Linked Blind Users
            </CardTitle>
          </CardHeader>
          <CardContent>
            {renderList(
              blindUsers,
              (blindUser) => (
                <div className="flex items-center justify-between rounded-lg border p-3">
                  <div className="flex flex-col gap-0.5">
                    <span className="font-medium text-sm">
                      {blindUser.fullName}
                    </span>
                    {blindUser.email && (
                      <span className="text-muted-foreground text-xs">
                        {blindUser.email}
                      </span>
                    )}
                  </div>
                  <Badge variant="secondary">Blind User</Badge>
                </div>
              ),
              "No blind users linked yet. Go to the Guardian tab to add one."
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <EyeIcon className="size-5" />
              Active Overwatch Sessions
            </CardTitle>
          </CardHeader>
          <CardContent>
            {renderList(
              activeOverwatch,
              (session) => (
                <div className="flex items-center justify-between rounded-lg border border-destructive/30 bg-destructive/5 p-3">
                  <div className="flex flex-col gap-0.5">
                    <span className="font-medium text-sm">
                      {session.blindUserFullName}
                    </span>
                    <span className="text-muted-foreground text-xs">
                      Started {new Date(session.startedAt).toLocaleTimeString()}
                    </span>
                  </div>
                  <Badge variant="destructive">Active Alert</Badge>
                </div>
              ),
              "No active Overwatch alerts. You will be notified when a linked user needs help."
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
