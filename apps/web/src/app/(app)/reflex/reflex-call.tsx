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
  useRoomContext,
  useTrackToggle,
  VideoTrack,
} from "@livekit/components-react";
import { Button } from "@tuntun-in/ui/components/button";
import { RoomEvent, Track } from "livekit-client";
import { Mic, MicOff, PhoneOff, Video, VideoOff } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const log = (...args: unknown[]) => console.log("[tuntun:reflex]", ...args);
const logError = (...args: unknown[]) =>
  console.error("[tuntun:reflex]", ...args);

interface TokenResponse {
  participant_token: string;
  server_url: string;
}

const sourceLabel = (source: Track.Source) => {
  switch (source) {
    case Track.Source.Microphone:
      return "mic";
    case Track.Source.Camera:
      return "camera";
    case Track.Source.ScreenShare:
      return "screen";
    case Track.Source.ScreenShareAudio:
      return "screen-audio";
    case Track.Source.Unknown:
      return "unknown";
    default:
      return String(source);
  }
};

/**
 * Subscribes to all relevant LiveKit room events and logs them with the
 * `[tuntun:reflex]` tag so the exact failure point (permissions, track
 * publish failures, agent connect, etc.) is visible in the browser console.
 */
function RoomEventLogger() {
  const room = useRoomContext();

  useEffect(() => {
    log("RoomEventLogger attached — room:", room.name || "(connecting)");

    const onConnected = () => log("Room CONNECTED — name:", room.name);
    const onDisconnected = (reason?: unknown) =>
      logError("Room DISCONNECTED — reason:", String(reason));
    const onReconnecting = () => log("Room RECONNECTING...");
    const onReconnected = () => log("Room RECONNECTED");
    const onConnectionQuality = (
      quality: unknown,
      participantIdentity: unknown
    ) =>
      log(
        "connection_quality_changed — quality:",
        quality,
        "participant:",
        participantIdentity
      );
    const onParticipantConnected = (participant: unknown) => {
      const p = participant as {
        identity?: string;
        sid?: string;
        kind?: number;
      };
      log(
        "participant_connected — identity:",
        p?.identity,
        "sid:",
        p?.sid,
        "kind:",
        p?.kind
      );
    };
    const onParticipantDisconnected = (participant: unknown) => {
      const p = participant as { identity?: string };
      log("participant_disconnected — identity:", p?.identity);
    };
    const onLocalTrackPublished = (publication: unknown, track: unknown) => {
      const pub = publication as {
        source?: Track.Source;
        kind?: number;
        sid?: string;
        name?: string;
        muted?: boolean;
      };
      const tr = track as { id?: string };
      log(
        "local_track_published — source:",
        sourceLabel(pub.source ?? Track.Source.Unknown),
        "kind:",
        pub.kind,
        "sid:",
        pub.sid,
        "name:",
        pub.name,
        "muted:",
        pub.muted,
        "trackId:",
        tr?.id
      );
    };
    const onLocalTrackUnpublished = (publication: unknown) => {
      const pub = publication as { source?: Track.Source; sid?: string };
      log(
        "local_track_unpublished — source:",
        sourceLabel(pub.source ?? Track.Source.Unknown),
        "sid:",
        pub.sid
      );
    };
    const onTrackSubscriptionFailed = (
      sid: unknown,
      participant: unknown,
      reason?: unknown
    ) => {
      const p = participant as { identity?: string };
      logError(
        "track_subscription_failed — trackSid:",
        sid,
        "participant:",
        p?.identity,
        "reason:",
        reason
      );
    };
    const onTrackPublished = (publication: unknown, participant: unknown) => {
      const pub = publication as {
        source?: Track.Source;
        kind?: number;
        sid?: string;
        muted?: boolean;
      };
      const p = participant as { identity?: string };
      log(
        "track_published (remote) — participant:",
        p?.identity,
        "source:",
        sourceLabel(pub.source ?? Track.Source.Unknown),
        "kind:",
        pub.kind,
        "muted:",
        pub.muted
      );
    };
    const onTrackSubscribed = (
      track: unknown,
      publication: unknown,
      participant: unknown
    ) => {
      const tr = track as { kind?: number; sid?: string };
      const pub = publication as { source?: Track.Source };
      const p = participant as { identity?: string };
      log(
        "track_subscribed — participant:",
        p?.identity,
        "source:",
        sourceLabel(pub.source ?? Track.Source.Unknown),
        "trackKind:",
        tr?.kind,
        "sid:",
        tr?.sid
      );
    };
    const onActiveSpeakersChanged = (speakers: unknown) => {
      const list = (speakers as Array<{ identity?: string; sid?: string }>).map(
        (s) => ({ identity: s.identity, sid: s.sid })
      );
      log("active_speakers_changed —", list.length, "active:", list);
    };
    const onMediaDevicesChanged = () => log("media_devices_changed");

    // Data channel messages (agent uses these for transcript/state updates)
    const onDataReceived = (payload: unknown) => {
      const text =
        typeof payload === "string"
          ? payload
          : (payload as Uint8Array | ArrayBuffer | Blob | undefined);
      log("data_received — payload:", text);
    };

    // Transcription events from the agent
    const onTranscriptionReceived = (
      segments: unknown,
      participant: unknown,
      publication: unknown
    ) => {
      const p = participant as { identity?: string };
      const segs = segments as Array<{
        id?: string;
        text?: string;
        final?: boolean;
      }>;
      log(
        "transcription_received — participant:",
        p?.identity,
        "segments:",
        segs?.map((s) => ({ id: s.id, text: s.text, final: s.final })),
        "publication:",
        publication
      );
    };

    room.on(RoomEvent.Connected, onConnected);
    room.on(RoomEvent.Disconnected, onDisconnected);
    room.on(RoomEvent.Reconnecting, onReconnecting);
    room.on(RoomEvent.Reconnected, onReconnected);
    room.on(RoomEvent.ConnectionQualityChanged, onConnectionQuality);
    room.on(RoomEvent.ParticipantConnected, onParticipantConnected);
    room.on(RoomEvent.ParticipantDisconnected, onParticipantDisconnected);
    room.on(RoomEvent.LocalTrackPublished, onLocalTrackPublished);
    room.on(RoomEvent.LocalTrackUnpublished, onLocalTrackUnpublished);
    room.on(RoomEvent.TrackSubscriptionFailed, onTrackSubscriptionFailed);
    room.on(RoomEvent.TrackPublished, onTrackPublished);
    room.on(RoomEvent.TrackSubscribed, onTrackSubscribed);
    room.on(RoomEvent.ActiveSpeakersChanged, onActiveSpeakersChanged);
    room.on(RoomEvent.MediaDevicesChanged, onMediaDevicesChanged);
    room.on(RoomEvent.DataReceived, onDataReceived);
    room.on(RoomEvent.TranscriptionReceived, onTranscriptionReceived);

    return () => {
      room.off(RoomEvent.Connected, onConnected);
      room.off(RoomEvent.Disconnected, onDisconnected);
      room.off(RoomEvent.Reconnecting, onReconnecting);
      room.off(RoomEvent.Reconnected, onReconnected);
      room.off(RoomEvent.ConnectionQualityChanged, onConnectionQuality);
      room.off(RoomEvent.ParticipantConnected, onParticipantConnected);
      room.off(RoomEvent.ParticipantDisconnected, onParticipantDisconnected);
      room.off(RoomEvent.LocalTrackPublished, onLocalTrackPublished);
      room.off(RoomEvent.LocalTrackUnpublished, onLocalTrackUnpublished);
      room.off(RoomEvent.TrackSubscriptionFailed, onTrackSubscriptionFailed);
      room.off(RoomEvent.TrackPublished, onTrackPublished);
      room.off(RoomEvent.TrackSubscribed, onTrackSubscribed);
      room.off(RoomEvent.ActiveSpeakersChanged, onActiveSpeakersChanged);
      room.off(RoomEvent.MediaDevicesChanged, onMediaDevicesChanged);
      room.off(RoomEvent.DataReceived, onDataReceived);
      room.off(RoomEvent.TranscriptionReceived, onTranscriptionReceived);
    };
  }, [room]);

  return null;
}

function LocalCameraPreview() {
  const { localParticipant, isMicrophoneEnabled, isCameraEnabled } =
    useLocalParticipant();

  const { buttonProps: micButtonProps } = useTrackToggle({
    source: Track.Source.Microphone,
  });
  const { buttonProps: camButtonProps } = useTrackToggle({
    source: Track.Source.Camera,
  });
  const { buttonProps: disconnectButtonProps } = useDisconnectButton({});

  const camPub = localParticipant?.getTrackPublication(Track.Source.Camera);

  useEffect(() => {
    log(
      "LocalCameraPreview state — micEnabled:",
      isMicrophoneEnabled,
      "camEnabled:",
      isCameraEnabled,
      "hasCamPub:",
      Boolean(camPub),
      "camPubSid:",
      camPub?.trackSid
    );
  }, [isMicrophoneEnabled, isCameraEnabled, camPub]);

  return (
    <div className="relative h-full w-full bg-black">
      {isCameraEnabled && camPub ? (
        <VideoTrack
          className="pointer-events-none h-full w-full object-cover"
          muted
          trackRef={{
            participant: localParticipant,
            publication: camPub,
            source: Track.Source.Camera,
          }}
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
    log(
      "PreJoin submit — roomName:",
      roomName,
      "username:",
      values.username,
      "videoEnabled:",
      values.videoEnabled,
      "audioEnabled:",
      values.audioEnabled
    );
    let res: Response;
    try {
      res = await fetch("/api/token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          room_name: roomName,
          participant_identity: values.username,
        }),
      });
    } catch (err) {
      logError("Token fetch network error:", err);
      return;
    }
    if (!res.ok) {
      logError("Token fetch failed — status:", res.status, res.statusText);
      const text = await res.text().catch(() => "<no body>");
      logError("Token fetch response body:", text);
      return;
    }
    const data = (await res.json()) as TokenResponse;
    log(
      "Token fetched — server_url:",
      data.server_url,
      "tokenLen:",
      data.participant_token.length
    );
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
            onError={(err) => {
              const name = err?.name ?? "Error";
              const message = err?.message ?? String(err);
              logError("PreJoin error:", err);
              logError(
                "PreJoin error detail — name:",
                name,
                "message:",
                message,
                "\nLikely causes:",
                "\n  1) Browser denied camera/mic permission (check site permissions)",
                "\n  2) Page not in a secure context (HTTPS or localhost) — getUserMedia is blocked on plain HTTP LAN IPs",
                "\n  3) No camera/mic device available"
              );
            }}
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
        <RoomEventLogger />
        <LocalCameraPreview />
        <RoomAudioRenderer />
      </LiveKitRoom>
    </div>
  );
}

export default ReflexCall;
