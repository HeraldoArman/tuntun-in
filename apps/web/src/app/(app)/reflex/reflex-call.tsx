"use client";

import "@livekit/components-styles/components";
import "@livekit/components-styles/prefabs";

import type { LocalUserChoices } from "@livekit/components-react";
import {
  LiveKitRoom,
  PreJoin,
  RoomAudioRenderer,
  useDisconnectButton,
  useLocalParticipant,
  useTrackToggle,
} from "@livekit/components-react";
import { Button } from "@tuntun-in/ui/components/button";
import { Track } from "livekit-client";
import { Mic, MicOff, PhoneOff, Video, VideoOff } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

interface TokenResponse {
  participant_token: string;
  server_url: string;
}

function LocalCameraPreview() {
  const { localParticipant, isMicrophoneEnabled, isCameraEnabled } =
    useLocalParticipant();
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const { buttonProps: micButtonProps } = useTrackToggle({
    source: Track.Source.Microphone,
  });
  const { buttonProps: camButtonProps } = useTrackToggle({
    source: Track.Source.Camera,
  });
  const { buttonProps: disconnectButtonProps } = useDisconnectButton({});

  const camPub = useMemo(
    () => localParticipant?.getTrackPublication(Track.Source.Camera),
    [localParticipant]
  );

  const mediaStreamTrack = camPub?.videoTrack?.mediaStreamTrack ?? null;

  useEffect(() => {
    const videoEl = videoRef.current;
    if (!(videoEl && mediaStreamTrack)) {
      return;
    }

    const stream = new MediaStream([mediaStreamTrack]);
    videoEl.srcObject = stream;
    videoEl
      .play()
      .catch((error) => console.error("Failed to play local video:", error));

    return () => {
      videoEl.srcObject = null;
    };
  }, [mediaStreamTrack]);

  return (
    <div className="relative h-full w-full bg-black">
      {isCameraEnabled && mediaStreamTrack ? (
        // eslint-disable-next-line jsx-a11y/media-has-caption
        <video
          autoPlay
          className="pointer-events-none h-full w-full object-cover"
          muted
          playsInline
          ref={videoRef}
        />
      ) : (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="flex h-24 w-24 items-center justify-center rounded-full bg-muted">
            <VideoOff className="h-10 w-10 text-muted-foreground" />
          </div>
        </div>
      )}

      <div className="absolute right-0 bottom-8 left-0 z-10 flex items-center justify-center gap-4">
        <Button
          aria-label={
            isMicrophoneEnabled ? "Turn microphone off" : "Turn microphone on"
          }
          size="icon"
          type="button"
          variant={isMicrophoneEnabled ? "default" : "destructive"}
          {...micButtonProps}
        >
          {isMicrophoneEnabled ? (
            <Mic className="h-5 w-5" />
          ) : (
            <MicOff className="h-5 w-5" />
          )}
        </Button>

        <Button
          aria-label={isCameraEnabled ? "Turn camera off" : "Turn camera on"}
          size="icon"
          type="button"
          variant={isCameraEnabled ? "default" : "destructive"}
          {...camButtonProps}
        >
          {isCameraEnabled ? (
            <Video className="h-5 w-5" />
          ) : (
            <VideoOff className="h-5 w-5" />
          )}
        </Button>

        <Button
          aria-label="End reflex session"
          size="icon"
          type="button"
          variant="destructive"
          {...disconnectButtonProps}
        >
          <PhoneOff className="h-5 w-5" />
        </Button>
      </div>
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
    <div className="h-screen w-screen bg-black">
      <LiveKitRoom
        audio={true}
        onDisconnected={handleDisconnected}
        serverUrl={tokenResponse.server_url}
        token={tokenResponse.participant_token}
        video={true}
      >
        <LocalCameraPreview />
        <RoomAudioRenderer />
      </LiveKitRoom>
    </div>
  );
}

export default ReflexCall;
