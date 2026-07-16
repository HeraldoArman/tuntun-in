import type { Metadata } from "next";

import "../index.css";

import Providers from "@/components/providers";
import { getToken } from "@/lib/auth-server";

export const metadata: Metadata = {
  title: "Tuntun.In",
  description: "AI mobility companion for the visually impaired.",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // ponytail: getToken() fetches the Convex site URL server-side; a transient
  // network timeout (WSL ↔ Cloudflare) used to 500 the whole layout. Fall back
  // to null — the client provider fetches the session itself when no token.
  let token: string | null = null;
  try {
    token = (await getToken()) ?? null;
  } catch {
    token = null;
  }
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Akt:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Alice&display=swap"
          rel="stylesheet"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="antialiased">
        <Providers initialToken={token}>{children}</Providers>
      </body>
    </html>
  );
}
