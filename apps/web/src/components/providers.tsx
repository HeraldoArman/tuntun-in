"use client";

import {
  type AuthClient,
  ConvexBetterAuthProvider,
} from "@convex-dev/better-auth/react";
import { env } from "@tuntun-in/env/web";
import { Toaster } from "@tuntun-in/ui/components/sonner";
import { ConvexReactClient } from "convex/react";

import { authClient } from "@/lib/auth-client";

import { ThemeProvider } from "./theme-provider";

const convex = new ConvexReactClient(env.NEXT_PUBLIC_CONVEX_URL);

export default function Providers({
  children,
  initialToken,
}: {
  children: React.ReactNode;
  initialToken?: string | null;
}) {
  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="light"
      disableTransitionOnChange
      forcedTheme="light"
    >
      <ConvexBetterAuthProvider
        // `@convex-dev/better-auth`'s `AuthClient` union instantiates
        // `createAuthClient` with a structural generic that resolves
        // `useSession().data` to `never` under better-auth 1.6.22, while our
        // inferred client carries the real session type. The two don't overlap,
        // so TS requires a double cast. The provider only uses token/session
        // fetching (never `useSession`), and casting only here keeps the real
        // session type intact for every other consumer (e.g. `useSession`).
        authClient={authClient as unknown as AuthClient}
        client={convex}
        initialToken={initialToken}
      >
        {children}
      </ConvexBetterAuthProvider>
      <Toaster richColors />
    </ThemeProvider>
  );
}
