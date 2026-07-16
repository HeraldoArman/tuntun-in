"use client";

import { env } from "@tuntun-in/env/web";
import { Button } from "@tuntun-in/ui/components/button";
import { FaGoogle } from "react-icons/fa";
import { toast } from "sonner";
import { authClient } from "@/lib/auth-client";

const googleEnabled = env.NEXT_PUBLIC_GOOGLE_OAUTH_ENABLED === "true";

export function GoogleSignInButton({ callbackURL }: { callbackURL: string }) {
  if (!googleEnabled) {
    return null;
  }

  return (
    <>
      <hr className="my-4 border-dashed" />
      <Button
        className="w-full"
        onClick={() => {
          authClient.signIn
            .social({
              provider: "google",
              callbackURL,
            })
            .catch((err) => {
              toast.error(err?.message || "Failed to sign in with Google");
            });
        }}
        variant="outline"
      >
        <FaGoogle className="mr-2 h-4 w-4" />
        Continue with Google
      </Button>
    </>
  );
}
