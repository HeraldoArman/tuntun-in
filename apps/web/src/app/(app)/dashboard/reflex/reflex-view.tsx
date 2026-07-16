"use client";

import {
  RoomAudioRenderer,
  SessionProvider,
  useLocalParticipant,
  useSession,
  useSessionContext,
  useVoiceAssistant,
} from "@livekit/components-react";
import { Button } from "@tuntun-in/ui/components/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@tuntun-in/ui/components/card";
import { TokenSource } from "livekit-client";
import {
  CameraIcon,
  CameraOffIcon,
  MicIcon,
  MicOffIcon,
  PhoneOffIcon,
  ScanEyeIcon,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

const AGENT_STATES: Record<string, string> = {
  connecting: "Connecting…",
  disconnected: "Disconnected",
  failed: "Connection failed",
  idle: "Idle",
  initializing: "Starting up…",
  listening: "Listening",
  speaking: "Speaking",
  thinking: "Thinking…",
};

function renderStatusPill(agentState: string) {
  const label = AGENT_STATES[agentState] ?? agentState;
  const isActive =
    agentState === "listening" ||
    agentState === "speaking" ||
    agentState === "thinking";
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm ${
        isActive
          ? "bg-green-100 text-green-700"
          : "bg-muted text-muted-foreground"
      }`}
    >
      <span
        className={`size-2 rounded-full ${
          isActive ? "animate-pulse bg-green-500" : "bg-muted-foreground/40"
        }`}
      />
      {label}
    </span>
  );
}

function ReflexControls() {
  const session = useSessionContext();
  const { localParticipant, isCameraEnabled, isMicrophoneEnabled } =
    useLocalParticipant();

  const [togglingMic, setTogglingMic] = useState(false);
  const [togglingCam, setTogglingCam] = useState(false);

  const handleToggleMic = async () => {
    setTogglingMic(true);
    try {
      if (isMicrophoneEnabled) {
        await localParticipant.setMicrophoneEnabled(false);
      } else {
        await localParticipant.setMicrophoneEnabled(true);
      }
    } catch {
      // device errors are surfaced via session events
    } finally {
      setTogglingMic(false);
    }
  };

  const handleToggleCam = async () => {
    setTogglingCam(true);
    try {
      if (isCameraEnabled) {
        await localParticipant.setCameraEnabled(false);
      } else {
        await localParticipant.setCameraEnabled(true);
      }
    } catch {
      // device errors are surfaced via session events
    } finally {
      setTogglingCam(false);
    }
  };

  const handleDisconnect = () => {
    session.end();
  };

  return (
    <div className="flex items-center gap-3">
      <Button
        disabled={togglingMic}
        onClick={handleToggleMic}
        size="icon"
        variant={isMicrophoneEnabled ? "default" : "secondary"}
      >
        {isMicrophoneEnabled ? (
          <MicIcon className="size-5" />
        ) : (
          <MicOffIcon className="size-5" />
        )}
      </Button>
      <Button
        disabled={togglingCam}
        onClick={handleToggleCam}
        size="icon"
        variant={isCameraEnabled ? "default" : "secondary"}
      >
        {isCameraEnabled ? (
          <CameraIcon className="size-5" />
        ) : (
          <CameraOffIcon className="size-5" />
        )}
      </Button>
      <Button onClick={handleDisconnect} size="icon" variant="destructive">
        <PhoneOffIcon className="size-5" />
      </Button>
    </div>
  );
}

function ReflexSessionInner() {
  const { state: agentState } = useVoiceAssistant();

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <ScanEyeIcon className="size-5" />
            Reflex AI — Live Session
          </CardTitle>
          <CardDescription>
            Your camera and microphone are streamed to the Tuntun agent. It
            watches for obstacles and speaks warnings in real time.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between rounded-lg border p-4">
            <div className="flex flex-col gap-1">
              <span className="font-medium text-sm">Agent status</span>
              <span className="text-muted-foreground text-xs">
                The agent is connected and processing your audio + video.
              </span>
            </div>
            {renderStatusPill(agentState)}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Controls</CardTitle>
          <CardDescription>
            Toggle your microphone and camera, or end the session.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ReflexControls />
        </CardContent>
      </Card>

      {/* Agent audio is played back through the room audio renderer */}
      <RoomAudioRenderer />
    </div>
  );
}

export function ReflexView() {
  const session = useSession(TokenSource.endpoint("/api/token"));
  const startedRef = useRef(false);

  // Start the session once on mount, publishing microphone + camera so the
  // agent receives audio and video for the reflex layer. A ref guard prevents
  // the effect from re-running across renders (useSession returns a new
  // object reference each render, which would otherwise loop start/end).
  useEffect(() => {
    if (startedRef.current) {
      return;
    }
    startedRef.current = true;

    const startSession = async () => {
      await session.start({
        tracks: {
          microphone: { enabled: true },
          camera: { enabled: true },
        },
      });
    };
    startSession().catch(() => {
      // connection errors are surfaced via session state
    });

    return () => {
      session.end();
    };
  }, [session]);

  return (
    <div className="p-6">
      <div className="mb-8">
        <h1 className="font-semibold text-2xl">Reflex AI</h1>
        <p className="mt-1 text-muted-foreground text-sm">
          Real-time vision-to-audio obstacle detection powered by Gemini Live.
        </p>
      </div>

      <div className="max-w-2xl">
        <SessionProvider session={session}>
          <ReflexSessionInner />
        </SessionProvider>
      </div>
    </div>
  );
}
