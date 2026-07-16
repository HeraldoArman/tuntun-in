import { api } from "@tuntun-in/backend/convex/_generated/api";
import { preloadAuthQuery } from "@/lib/auth-server";
import { SettingsView } from "./settings-view";

export default async function SettingsPage() {
  const [preloadedUser, preloadedProfile] = await Promise.all([
    preloadAuthQuery(api.auth.getCurrentUser),
    preloadAuthQuery(api.userProfiles.getCurrent),
  ]);

  return (
    <SettingsView
      preloadedProfile={preloadedProfile}
      preloadedUser={preloadedUser}
    />
  );
}
