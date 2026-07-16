import { SpectatorView } from "./spectator-view";

export const dynamic = "force-dynamic";

/**
 * Public Overwatch spectator page — the destination of the secret WebRTC
 * link the agent sends to the guardian via WhatsApp. No auth: the LiveKit
 * token in the URL is the secret. Anyone with the link can view the blind
 * user's camera and guide them verbally for the token's TTL.
 *
 * Query params (all set by the agent when it mints the link):
 *   token  — LiveKit JWT (subscribe + publish audio)
 *   server — LiveKit server URL (wss://...)
 *   room   — room name (for display)
 */
export default async function SpectatorPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string; server?: string; room?: string }>;
}) {
  const params = await searchParams;
  return (
    <SpectatorView
      roomName={params.room}
      serverUrl={params.server}
      token={params.token}
    />
  );
}
