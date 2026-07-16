"use client";

import "@livekit/components-styles/components";
import "@livekit/components-styles/prefabs";

import {
  LiveKitRoom,
  RoomAudioRenderer,
  useDisconnectButton,
  useLocalParticipant,
  useParticipants,
  useTrackToggle,
  VideoTrack,
} from "@livekit/components-react";
import { Button } from "@tuntun-in/ui/components/button";
import { cn } from "@tuntun-in/ui/lib/utils";
import { Track } from "livekit-client";
import {
  ArrowLeft,
  EyeIcon,
  Mic,
  MicOff,
  PhoneOff,
  ShieldAlertIcon,
} from "lucide-react";
import Link from "next/link";

const log = (...args: unknown[]) => console.log("[tuntun:spectator]", ...args);
const logError = (...args: unknown[]) =>
  console.error("[tuntun:spectator]", ...args);

interface SpectatorViewProps {
  roomName?: string;
  serverUrl?: string;
  token?: string;
}

/**
 * Find the first remote participant publishing a camera track — that is the
 * blind user's chest-mounted camera. The agent publishes audio only, so any
 * remote camera track belongs to the blind user.
 */
function useBlindUserCamera() {
  const participants = useParticipants();
  for (const p of participants) {
    if (p.isLocal) {
      continue;
    }
    const camPub = p.getTrackPublication(Track.Source.Camera);
    if (camPub) {
      return { participant: p, publication: camPub };
    }
  }
  return null;
}

function SpectatorStage({ roomName }: { roomName?: string }) {
  const cam = useBlindUserCamera();
  const { isMicrophoneEnabled } = useLocalParticipant();

  const { buttonProps: micButtonProps } = useTrackToggle({
    source: Track.Source.Microphone,
  });
  const { buttonProps: disconnectButtonPropsRaw } = useDisconnectButton({});
  const { className: disconnectButtonClassName, ...disconnectButtonProps } =
    disconnectButtonPropsRaw;
  const disconnectClassName = cn(
    disconnectButtonClassName,
    "size-12 rounded-full [&_svg]:size-5"
  );

  return (
    <div className="relative h-full w-full overflow-hidden bg-black">
      {cam ? (
        <VideoTrack
          className="pointer-events-none h-full w-full object-cover"
          trackRef={{
            participant: cam.participant,
            publication: cam.publication,
            source: Track.Source.Camera,
          }}
        />
      ) : (
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-4">
          <div className="flex size-20 items-center justify-center rounded-full border border-white/10 bg-white/5 backdrop-blur-sm">
            <EyeIcon className="size-9 text-white/60" />
          </div>
          <p className="text-sm text-white/60">
            Waiting for the live camera...
          </p>
        </div>
      )}

      {/* Top status bar — emergency indicator + room badge */}
      <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-between gap-3 bg-gradient-to-b from-black/60 to-transparent p-4 pt-5">
        <div className="flex items-center gap-2 rounded-full border border-destructive/40 bg-destructive/10 px-3 py-1.5 backdrop-blur-md">
          <ShieldAlertIcon className="size-3.5 text-destructive" />
          <span className="font-medium text-sm text-white">Overwatch live</span>
        </div>
        {roomName ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-black/40 px-3 py-1.5 font-medium text-white/80 text-xs backdrop-blur-md">
            <EyeIcon className="size-3.5" />
            {roomName}
          </span>
        ) : null}
      </div>

      <p className="absolute inset-x-0 top-16 z-10 text-balance text-center text-muted-foreground text-xs">
        You are guiding verbally — toggle your mic and talk them through it.
      </p>

      {/* Bottom control dock — mic + leave */}
      <div className="absolute inset-x-0 bottom-0 z-10 bg-gradient-to-t from-black/70 to-transparent p-6 pt-20">
        <div className="mx-auto flex w-fit items-center gap-2 rounded-2xl border border-white/10 bg-black/40 p-2 shadow-lg backdrop-blur-md">
          <Button
            aria-label={
              isMicrophoneEnabled ? "Turn microphone off" : "Turn microphone on"
            }
            className="size-12 rounded-xl [&_svg]:size-5"
            type="button"
            variant={isMicrophoneEnabled ? "default" : "destructive"}
            {...micButtonProps}
          >
            {isMicrophoneEnabled ? <Mic /> : <MicOff />}
          </Button>

          <div className="mx-1 h-8 w-px bg-white/10" />

          <Button
            aria-label="Leave spectator session"
            className={disconnectClassName}
            type="button"
            variant="destructive"
            {...disconnectButtonProps}
          >
            <PhoneOff />
          </Button>
        </div>
      </div>
    </div>
  );
}

export function SpectatorView({
  token,
  serverUrl,
  roomName,
}: SpectatorViewProps) {
  if (!(token && serverUrl)) {
    logError("Missing token or serverUrl — cannot join spectator session");
    return (
      <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background p-4">
        <div
          aria-hidden
          className="absolute inset-0 -z-10 [background:radial-gradient(125%_125%_at_50%_100%,transparent_0%,var(--color-background)_75%)]"
        />
        <div className="w-full max-w-md text-center">
          <div className="mx-auto mb-6 flex size-14 items-center justify-center rounded-2xl border bg-muted shadow-sm">
            <ShieldAlertIcon className="size-7 text-destructive" />
          </div>
          <h1 className="font-semibold text-2xl tracking-tight">
            Invalid spectator link
          </h1>
          <p className="mt-2 text-balance text-muted-foreground text-sm">
            This Overwatch link is missing or expired. Ask the user to trigger
            Overwatch again to receive a fresh link.
          </p>
          <Link
            className="mt-6 inline-flex items-center gap-1.5 text-muted-foreground text-sm transition-colors hover:text-foreground"
            href="/dashboard"
          >
            <ArrowLeft className="size-4" />
            Back to dashboard
          </Link>
        </div>
      </div>
    );
  }

  log(
    "Joining spectator session — room:",
    roomName,
    "serverLen:",
    serverUrl.length,
    "tokenLen:",
    token.length
  );

  return (
    <div className="h-screen w-screen bg-black">
      <LiveKitRoom
        audio={true}
        connect={true}
        serverUrl={serverUrl}
        token={token}
        video={false}
      >
        <SpectatorStage roomName={roomName} />
        <RoomAudioRenderer />
      </LiveKitRoom>
    </div>
  );
}

export default SpectatorView;
