FROM node:24-slim AS builder
RUN npm install -g pnpm
WORKDIR /app
ENV SKIP_ENV_VALIDATION=1

COPY . .
RUN --mount=type=cache,id=s/7662d503-b69e-4830-80c0-bd7050eb19b0-/pnpm-store,target=/pnpm-store pnpm install --store-dir /pnpm-store

ARG NEXT_PUBLIC_CONVEX_URL
ENV NEXT_PUBLIC_CONVEX_URL=${NEXT_PUBLIC_CONVEX_URL}
ARG NEXT_PUBLIC_CONVEX_SITE_URL
ENV NEXT_PUBLIC_CONVEX_SITE_URL=${NEXT_PUBLIC_CONVEX_SITE_URL}
ENV NODE_ENV=production
RUN cd apps/web && pnpm run build

FROM node:24-slim AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/apps/web/.next/standalone ./
COPY --from=builder /app/apps/web/.next/static ./apps/web/.next/static
# Next.js standalone tracing excludes /public (and /static) by design — the
# standalone server.js only serves files from a sibling public/ directory, so
# the logo, mascot, and favicon manifest icons 404/400 at runtime without this.
COPY --from=builder /app/apps/web/public ./apps/web/public

ENV HOSTNAME=0.0.0.0
ENV PORT=3001
EXPOSE 3001

CMD ["node", "apps/web/server.js"]
