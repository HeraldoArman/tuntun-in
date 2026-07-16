import { redirect } from "next/navigation";
import { isAuthenticated } from "@/lib/auth-server";
import { ReflexCall } from "./reflex-call";

export default async function ReflexCallPage() {
  const authed = await isAuthenticated();
  if (!authed) {
    redirect("/login");
  }

  return <ReflexCall />;
}
