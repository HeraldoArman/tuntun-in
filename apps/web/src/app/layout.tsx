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
  const token = await getToken();
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
