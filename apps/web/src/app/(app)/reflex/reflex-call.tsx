"use client";

import type { LocalUserChoices } from "@livekit/components-react";
import {
  ConnectionStateToast,
  ControlBar,
  LiveKitRoom,
  PreJoin,
  useLocalParticipant,
  VideoTrack,
} from "@livekit/components-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

interface TokenResponse {
  participant_token: string;
  server_url: string;
}

function LocalCameraTile() {
  const { localParticipant, isCameraEnabled } = useLocalParticipant();
  const publication = localParticipant.getTrackPublication("camera" as never);
  const track = publication?.track;

  return (
    <div className="flex flex-1 items-center justify-center bg-black">
      {isCameraEnabled && track && publication ? (
        <VideoTrack
          className="h-full w-full object-cover"
          trackRef={{
            participant: localParticipant,
            publication,
            source: "camera" as never,
          }}
        />
      ) : (
        <div className="flex flex-col items-center gap-3 text-white/60">
          <span className="text-4xl">📷</span>
          <p className="text-sm">Camera is off</p>
        </div>
      )}
    </div>
  );
}

export function ReflexCall() {
  const router = useRouter();
  const [tokenResponse, setTokenResponse] = useState<TokenResponse | null>(
    null
  );

  const handlePreJoinSubmit = async (values: LocalUserChoices) => {
    const roomName = `reflex-${Date.now()}`;
    const res = await fetch("/api/token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        room_name: roomName,
        participant_identity: values.username,
      }),
    });
    const data = (await res.json()) as TokenResponse;
    setTokenResponse(data);
  };

  const handleDisconnected = () => {
    router.push("/dashboard/reflex");
  };

  // Show the pre-join screen until the user picks their devices and joins.
  if (!tokenResponse) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-4">
        <div className="w-full max-w-md">
          <h1 className="mb-6 text-center font-semibold text-2xl">
            Reflex AI Session
          </h1>
          <PreJoin
            defaults={{ videoEnabled: true, audioEnabled: true }}
            joinLabel="Start Reflex Session"
            onError={(err) => console.error("PreJoin error:", err)}
            onSubmit={handlePreJoinSubmit}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen flex-col">
      <LiveKitRoom
        audio={true}
        className="flex h-full flex-col"
        onDisconnected={handleDisconnected}
        serverUrl={tokenResponse.server_url}
        token={tokenResponse.participant_token}
        video={true}
      >
        <LocalCameraTile />
        <ControlBar
          controls={{ chat: false, screenShare: false, settings: false }}
          variation="minimal"
        />
        <ConnectionStateToast />
      </LiveKitRoom>
    </div>
  );
}
