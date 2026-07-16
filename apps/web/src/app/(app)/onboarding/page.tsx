import { api } from "@tuntun-in/backend/convex/_generated/api";
import { preloadAuthQuery } from "@/lib/auth-server";
import { OnboardingView } from "./onboarding-view";

export default async function OnboardingPage() {
  const preloadedUser = await preloadAuthQuery(api.auth.getCurrentUser);

  return <OnboardingView preloadedUser={preloadedUser} />;
}
