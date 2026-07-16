import { createEnv } from "@t3-oss/env-nextjs";
import { z } from "zod";

const convexUrlSchema = (exampleHost: string) =>
  z.url().refine((url) => new URL(url).hostname !== exampleHost, {
    message: `Replace the ${exampleHost} placeholder before running the app`,
  });

export const env = createEnv({
  client: {
    NEXT_PUBLIC_CONVEX_URL: convexUrlSchema("example.convex.cloud"),
    NEXT_PUBLIC_CONVEX_SITE_URL: convexUrlSchema("example.convex.site"),
  },
  runtimeEnv: {
    NEXT_PUBLIC_CONVEX_URL: process.env.NEXT_PUBLIC_CONVEX_URL,
    NEXT_PUBLIC_CONVEX_SITE_URL: process.env.NEXT_PUBLIC_CONVEX_SITE_URL,
  },
  skipValidation: !!process.env.SKIP_ENV_VALIDATION,
  emptyStringAsUndefined: true,
});
