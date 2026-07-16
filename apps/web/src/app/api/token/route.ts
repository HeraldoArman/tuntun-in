import { RoomAgentDispatch, RoomConfiguration } from "@livekit/protocol";
import { AccessToken } from "livekit-server-sdk";
import { NextResponse } from "next/server";

export const revalidate = 0;

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;

  const roomName = String(body.room_name ?? `reflex-${Date.now()}`);
  const identity = String(body.participant_identity ?? `user-${Date.now()}`);

  const apiKey = process.env.LIVEKIT_API_KEY;
  const apiSecret = process.env.LIVEKIT_API_SECRET;
  const livekitUrl = process.env.LIVEKIT_URL;

  if (!(apiKey && apiSecret && livekitUrl)) {
    return NextResponse.json(
      { error: "LiveKit not configured" },
      { status: 500 }
    );
  }

  const at = new AccessToken(apiKey, apiSecret, {
    identity,
    ttl: "10m",
  });

  at.addGrant({
    roomJoin: true,
    room: roomName,
    canPublish: true,
    canSubscribe: true,
    canPublishData: true,
  });

  const config = new RoomConfiguration({
    agents: [new RoomAgentDispatch({ agentName: "tuntun-agent" })],
  });
  at.roomConfig = config;

  const token = await at.toJwt();

  return NextResponse.json(
    {
      server_url: livekitUrl,
      participant_token: token,
    },
    {
      status: 201,
      headers: { "Cache-Control": "no-store" },
    }
  );
}
