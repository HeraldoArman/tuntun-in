import { api } from "@tuntun-in/backend/convex/_generated/api";
import { preloadAuthQuery } from "@/lib/auth-server";
import { DashboardView } from "./dashboard-view";

export default async function DashboardPage() {
  const [preloadedUser, preloadedProfile] = await Promise.all([
    preloadAuthQuery(api.auth.getCurrentUser),
    preloadAuthQuery(api.userProfiles.getCurrent),
  ]);

  return (
    <DashboardView
      preloadedProfile={preloadedProfile}
      preloadedUser={preloadedUser}
    />
  );
}
