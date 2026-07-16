"use client";

import "@livekit/components-styles/components";
import "@livekit/components-styles/prefabs";

import type { LocalUserChoices } from "@livekit/components-react";
import {
  LiveKitRoom,
  PreJoin,
  useLocalParticipant,
  VideoTrack,
} from "@livekit/components-react";
import { Button } from "@tuntun-in/ui/components/button";
import { Track } from "livekit-client";
import { Mic, MicOff, PhoneOff, Video, VideoOff } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

interface TokenResponse {
  participant_token: string;
  server_url: string;
}

function LocalCameraPreview() {
  const { localParticipant } = useLocalParticipant();
  const publication = localParticipant.getTrackPublication(Track.Source.Camera);
  const audioPub = localParticipant.getTrackPublication(
    Track.Source.Microphone
  );

  const [micEnabled, setMicEnabled] = useState(audioPub?.isMuted === false);
  const [camEnabled, setCamEnabled] = useState(publication?.isMuted === false);

  useEffect(() => {
    const interval = setInterval(() => {
      const camPub = localParticipant.getTrackPublication(Track.Source.Camera);
      const micPub = localParticipant.getTrackPublication(
        Track.Source.Microphone
      );
      setCamEnabled(camPub?.isMuted === false);
      setMicEnabled(micPub?.isMuted === false);
    }, 300);
    return () => clearInterval(interval);
  }, [localParticipant]);

  const toggleMic = async () => {
    await localParticipant.setMicrophoneEnabled(!micEnabled);
  };
  const toggleCam = async () => {
    await localParticipant.setCameraEnabled(!camEnabled);
  };

  return (
    <div className="relative flex-1 bg-black">
      <div className="absolute inset-0 flex items-center justify-center">
        {publication?.isMuted === false && publication.videoTrack ? (
          <VideoTrack
            className="h-full w-full object-cover"
            publication={publication}
            trackRef={{
              participant: localParticipant,
              publication: publication ?? undefined,
              source: Track.Source.Camera,
            }}
          />
        ) : (
          <div className="flex h-24 w-24 items-center justify-center rounded-full bg-muted">
            <VideoOff className="h-10 w-10 text-muted-foreground" />
          </div>
        )}
      </div>

      <div className="absolute right-0 bottom-6 left-0 flex items-center justify-center gap-4">
        <Button
          aria-label={micEnabled ? "Turn microphone off" : "Turn microphone on"}
          onClick={toggleMic}
          size="icon"
          variant={micEnabled ? "default" : "destructive"}
        >
          {micEnabled ? (
            <Mic className="h-5 w-5" />
          ) : (
            <MicOff className="h-5 w-5" />
          )}
        </Button>
        <Button
          aria-label={camEnabled ? "Turn camera off" : "Turn camera on"}
          onClick={toggleCam}
          size="icon"
          variant={camEnabled ? "default" : "destructive"}
        >
          {camEnabled ? (
            <Video className="h-5 w-5" />
          ) : (
            <VideoOff className="h-5 w-5" />
          )}
        </Button>
        <Button
          aria-label="End reflex session"
          onClick={() => localParticipant.room.disconnect()}
          size="icon"
          variant="destructive"
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
      </LiveKitRoom>
    </div>
  );
}

export default ReflexCall;
