"use client";

import "@livekit/components-styles/components";
import "@livekit/components-styles/prefabs";

import type { LocalUserChoices } from "@livekit/components-react";
import {
  ControlBar,
  FocusLayout,
  FocusLayoutContainer,
  LiveKitRoom,
  PreJoin,
  useLocalParticipant,
} from "@livekit/components-react";
import { Track } from "livekit-client";
import { useRouter } from "next/navigation";
import { useState } from "react";

interface TokenResponse {
  participant_token: string;
  server_url: string;
}

function LocalCameraFocus() {
  const { localParticipant } = useLocalParticipant();
  const publication = localParticipant.getTrackPublication(Track.Source.Camera);

  const trackRef = {
    participant: localParticipant,
    publication: publication ?? undefined,
    source: Track.Source.Camera,
  };

  return (
    <FocusLayoutContainer className="flex-1">
      <FocusLayout className="h-full" trackRef={trackRef} />
    </FocusLayoutContainer>
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
        <LocalCameraFocus />
        <ControlBar
          controls={{ chat: false, screenShare: false, settings: false }}
          variation="minimal"
        />
      </LiveKitRoom>
    </div>
  );
}
