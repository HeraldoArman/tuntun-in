import { convexBetterAuthNextJs } from "@convex-dev/better-auth/nextjs";
import { env } from "@tuntun-in/env/web";

const {
  handler,
  // ponytail: raw preloader renamed; re-export a retry-wrapped version below so
  // a transient undici connect timeout (WSL2 ↔ Cloudflare under dev compile load)
  // doesn't 500 the whole SSR route. Views still get a real Preloaded object.
  preloadAuthQuery: rawPreloadAuthQuery,
  isAuthenticated,
  getToken,
  fetchAuthQuery,
  fetchAuthMutation,
  fetchAuthAction,
} = convexBetterAuthNextJs({
  convexUrl: env.NEXT_PUBLIC_CONVEX_URL,
  convexSiteUrl: env.NEXT_PUBLIC_CONVEX_SITE_URL,
});

function isTransientNetworkError(err: unknown): boolean {
  if (!(err instanceof Error)) {
    return false;
  }
  const code = (err as { cause?: { code?: string } }).cause?.code;
  return (
    code === "UND_ERR_CONNECT_TIMEOUT" ||
    code === "ETIMEDOUT" ||
    code === "ECONNRESET" ||
    code === "EAI_AGAIN"
  );
}

// Retry transient network failures once before surfacing. Auth preloads are
// SSR-only UX optimizations; the client re-fetches on hydration regardless, but
// a thrown error here 500s the route, so a single retry absorbs the blip.
export async function preloadAuthQuery<T>(
  query: Parameters<typeof rawPreloadAuthQuery>[0]
) {
  try {
    return await rawPreloadAuthQuery(query as never);
  } catch (err) {
    if (!isTransientNetworkError(err)) {
      throw err;
    }
    return await rawPreloadAuthQuery(query as never);
  }
}

export {
  fetchAuthAction,
  fetchAuthMutation,
  fetchAuthQuery,
  getToken,
  handler,
  isAuthenticated,
};
