import { api } from "@tuntun-in/backend/convex/_generated/api";
import { preloadAuthQuery } from "@/lib/auth-server";
import { GuardianView } from "./guardian-view";

export default async function GuardianPage() {
  // Preload auth to ensure the user is authenticated before rendering
  await Promise.all([
    preloadAuthQuery(api.auth.getCurrentUser),
    preloadAuthQuery(api.userProfiles.getCurrent),
  ]);

  return <GuardianView />;
}
