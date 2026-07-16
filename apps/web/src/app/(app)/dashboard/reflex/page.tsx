import { api } from "@tuntun-in/backend/convex/_generated/api";
import { preloadAuthQuery } from "@/lib/auth-server";
import { ReflexView } from "./reflex-view";

export default async function ReflexPage() {
  // Preload auth to ensure the user is authenticated before rendering
  await preloadAuthQuery(api.userProfiles.getCurrent);

  return <ReflexView />;
}
