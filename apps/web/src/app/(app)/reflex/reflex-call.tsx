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
import { api } from "@tuntun-in/backend/convex/_generated/api";
import { Button } from "@tuntun-in/ui/components/button";
import { cn } from "@tuntun-in/ui/lib/utils";
import { useMutation, useQuery } from "convex/react";
import type { VideoCaptureOptions } from "livekit-client";
import { ConnectionState, RoomEvent, Track } from "livekit-client";
import {
  ArrowLeft,
  Camera,
  MapPin,
  Mic,
  MicOff,
  PhoneOff,
  ScanEye,
  Video,
  VideoOff,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

/**
 * Chest-mounted phones should use the rear (environment) camera by default,
 * not the selfie cam, so the Reflex AI sees the path ahead of the user.
 * A hard `facingMode: "environment"` constraint throws OverconstrainedError on
 * desktops (no environment cam), leaving the track unpublished and the call view
 * stuck on "Camera is off" — so only request it on mobile, where a rear cam
 * actually exists. Desktop falls back to the default (front) cam.
 */
const isMobile =
  typeof navigator !== "undefined" &&
  /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent);
const REAR_CAMERA_CAPTURE: VideoCaptureOptions = isMobile
  ? { facingMode: "environment" }
  : {};

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

/**
 * Publishes the device GPS position to the agent over the LiveKit data
 * channel (topic "gps") so Deep Navigator can use it as the route origin.
 * Headless — renders nothing. Best-effort: permission denial or missing
 * geolocation is logged and the agent will ask the user to share location.
 *
 * Throttled to one fix per `GPS_PUBLISH_MS` to avoid flooding the data
 * channel. Uses watchPosition for live updates, with a getCurrentPosition
 * fallback for browsers that misbehave with watch.
 */
const GPS_PUBLISH_MS = 5000;
const GPS_TOPIC = "gps";

function GpsPublisher() {
  const room = useRoomContext();
  const { localParticipant } = useLocalParticipant();

  useEffect(() => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      logError("Geolocation API unavailable — Deep Navigator origin disabled");
      return;
    }
    if (!localParticipant) {
      log("GpsPublisher — no localParticipant yet, skipping");
      return;
    }

    log(
      "GpsPublisher mounted — room:",
      room.name || "(connecting)",
      "watching position, publish every",
      GPS_PUBLISH_MS,
      "ms"
    );

    let lastPublished = 0;
    // Cache the most recent fix so it can be re-published when the agent
    // joins late (the first watchPosition fire often happens before the
    // agent's room is connected, so the agent never receives it) or when the
    // device is stationary and watchPosition hasn't fired again.
    let lastFix: { lat: number; lng: number; accuracy?: number } | null = null;
    let watchId: number | null = null;

    const publishFix = (lat: number, lng: number, accuracy?: number) => {
      const now = Date.now();
      if (now - lastPublished < GPS_PUBLISH_MS) {
        log(
          "GpsPublisher — throttle skip (too soon since last publish):",
          now - lastPublished,
          "ms"
        );
        return;
      }
      // Drop the fix if the room isn't connected yet — publishing now would
      // throw NegotiationError on a closed engine. watchPosition will fire
      // again after connect, so we just skip this one.
      if (room.state !== ConnectionState.Connected) {
        log(
          "GpsPublisher — room not connected yet (state:",
          room.state,
          "), skipping gps fix"
        );
        return;
      }
      lastPublished = now;
      // publishData expects a Uint8Array (NonSharedUint8Array). Passing a
      // string silently produces empty bytes on the receiver (protobuf-es
      // bytes field coerces a string to nothing), so the agent's data handler
      // gets an empty payload and never stores the GPS fix. Encode UTF-8.
      const payload = new TextEncoder().encode(
        JSON.stringify({ type: "gps", lat, lng })
      );
      localParticipant
        .publishData(payload, { reliable: true, topic: GPS_TOPIC })
        .then(() =>
          log(
            "GpsPublisher — published gps fix: lat=",
            lat,
            "lng=",
            lng,
            "accuracy=",
            accuracy ?? "n/a"
          )
        )
        .catch((err: unknown) =>
          logError("GpsPublisher — publishData failed:", err)
        );
    };

    const onSuccess = (pos: GeolocationPosition) => {
      lastFix = {
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
        accuracy: pos.coords.accuracy,
      };
      publishFix(
        pos.coords.latitude,
        pos.coords.longitude,
        pos.coords.accuracy
      );
    };
    const onError = (err: GeolocationPositionError) => {
      logError(
        "GpsPublisher — geolocation error — code:",
        err.code,
        "message:",
        err.message,
        "(1=permission denied, 2=unavailable, 3=timeout)"
      );
    };

    try {
      watchId = navigator.geolocation.watchPosition(onSuccess, onError, {
        enableHighAccuracy: true,
        maximumAge: GPS_PUBLISH_MS,
        timeout: 15_000,
      });
      log("GpsPublisher — watchPosition started, id:", watchId);
    } catch (err) {
      logError("GpsPublisher — watchPosition threw:", err);
    }

    // Periodic re-publish: watchPosition only fires when the position
    // changes, so a stationary device may never send a second fix. The agent
    // joins the room after the web client (dispatched by LiveKit Cloud), so
    // it often misses the first publish. Re-publishing the cached fix every
    // GPS_PUBLISH_MS guarantees the agent receives it within a few seconds.
    const republish = () => {
      if (!lastFix) {
        return;
      }
      // Reset the throttle so a late-arriving agent gets the fix even if we
      // just published (a new participant joined — they missed that one).
      lastPublished = 0;
      publishFix(lastFix.lat, lastFix.lng, lastFix.accuracy);
    };

    const intervalId = window.setInterval(() => {
      if (lastFix && room.state === ConnectionState.Connected) {
        republish();
      }
    }, GPS_PUBLISH_MS);

    // Re-publish immediately when a new participant connects so a
    // late-arriving agent doesn't have to wait for the next interval.
    const onParticipantConnected = () => {
      log("GpsPublisher — participant connected, re-publishing cached gps fix");
      republish();
    };
    room.on(RoomEvent.ParticipantConnected, onParticipantConnected);

    return () => {
      if (watchId !== null) {
        navigator.geolocation.clearWatch(watchId);
        log("GpsPublisher — watchPosition cleared, id:", watchId);
      }
      window.clearInterval(intervalId);
      room.off(RoomEvent.ParticipantConnected, onParticipantConnected);
    };
  }, [room, localParticipant]);

  return null;
}

/**
 * Publishes the blind user's Convex profile id to the agent over the LiveKit
 * data channel (topic "profile") so the Overwatch tool can resolve the linked
 * guardian and send them a WhatsApp alert. Headless — renders nothing.
 *
 * Published once when the local participant + profile are ready, and again
 * whenever a new participant connects (the agent joins after the user, so the
 * first publish could be missed — re-publishing on ParticipantConnected
 * guarantees the agent receives it).
 */
const PROFILE_TOPIC = "profile";

function ProfilePublisher() {
  const room = useRoomContext();
  const { localParticipant } = useLocalParticipant();
  const profile = useQuery(api.userProfiles.getCurrent);

  useEffect(() => {
    if (!localParticipant || profile === undefined || profile === null) {
      return;
    }
    const profileId = profile._id;
    // Encode as Uint8Array — see GpsPublisher note. A string payload arrives
    // empty on the receiver, so the agent would never see the profileId.
    const payload = new TextEncoder().encode(
      JSON.stringify({ type: "profile", profileId })
    );

    const publish = () => {
      // Don't publish before the room's RTC engine is connected — doing so
      // throws NegotiationError ("cannot negotiate on closed engine") when the
      // effect runs during the connecting phase (or after an HMR remount on a
      // closed engine). Defer to RoomEvent.Connected below.
      if (room.state !== ConnectionState.Connected) {
        log(
          "ProfilePublisher — room not connected yet (state:",
          room.state,
          "), deferring profileId publish until Connected"
        );
        return;
      }
      localParticipant
        .publishData(payload, { reliable: true, topic: PROFILE_TOPIC })
        .then(() =>
          log(
            "ProfilePublisher — published profileId:",
            profileId,
            "room:",
            room.name
          )
        )
        .catch((err: unknown) =>
          logError("ProfilePublisher — publishData failed:", err)
        );
    };

    publish();

    // Publish once the room finishes connecting (covers the case where the
    // effect ran during the connecting phase above).
    const onConnected = () => {
      log("ProfilePublisher — room Connected, publishing profileId");
      publish();
    };
    // Re-publish when a new participant joins so a late-arriving agent still
    // gets the profile id.
    const onParticipantConnected = () => {
      log("ProfilePublisher — participant connected, re-publishing profileId");
      publish();
    };
    room.on(RoomEvent.Connected, onConnected);
    room.on(RoomEvent.ParticipantConnected, onParticipantConnected);

    return () => {
      room.off(RoomEvent.Connected, onConnected);
      room.off(RoomEvent.ParticipantConnected, onParticipantConnected);
    };
  }, [room, localParticipant, profile]);

  return null;
}

/**
 * Plays a soft, comforting "thinking" sound while the agent is working — so a
 * blind user knows the agent heard them and is processing (not frozen/silent).
 *
 * Detection (no AgentState event exists on the client, so we infer from media):
 *  - Local user's transcription turns final  -> user finished speaking -> the
 *    agent is now "thinking" -> start the gentle tone loop.
 *  - Agent transcription received, or agent becomes an active speaker -> agent
 *    is responding -> stop the tone.
 *  - Safety auto-stop after `MAX Thinking` seconds with no agent reply, so a
 *    missed event never leaves the tone looping forever.
 *
 * The sound: a slow, soft two-note sine pulse (consonant major-third interval),
 * low gain, smooth attack/release. No sharp transients — calming, not alarming.
 * Headless — renders nothing.
 */
const THINKING_INTERVAL_MS = 1000;
const THINKING_MAX_MS = 12_000;
// Soft consonant interval (C5 / E5) — calm, pleasant.
const THINKING_FREQS = [523.25, 659.25];
const THINKING_PEAK_GAIN = 0.08;

// Module-level shared AudioContext for the thinking tone. Browsers suspend an
// AudioContext created outside a user gesture, and resume() must be called
// while a gesture is "active" (transient activation). Calling resume() from a
// TranscriptionReceived event — which is NOT a user gesture — leaves the
// context suspended and the beeps silent. So we warm the context on the first
// pointer/key gesture at module load. This module loads before PreJoin
// renders, so the "Start Reflex Session" click (a real gesture) triggers the
// warmer and the context is already running by the time the first beep fires.
let sharedAudioCtx: AudioContext | null = null;
let audioWarmerInstalled = false;

function createAudioContext(): AudioContext | null {
  const Ctor =
    window.AudioContext ??
    (window as unknown as { webkitAudioContext?: typeof AudioContext })
      .webkitAudioContext;
  return Ctor ? new Ctor() : null;
}

function warmAudioOnGesture() {
  if (sharedAudioCtx) {
    return;
  }
  const ctx = createAudioContext();
  if (!ctx) {
    return;
  }
  sharedAudioCtx = ctx;
  if (ctx.state === "suspended") {
    ctx
      .resume()
      .then(() => log("[tuntun:thinking] audio warmed — state:", ctx.state))
      .catch((err: unknown) =>
        logError("[tuntun:thinking] warm resume failed:", err)
      );
  }
  window.removeEventListener("pointerdown", warmAudioOnGesture);
  window.removeEventListener("keydown", warmAudioOnGesture);
}

if (typeof window !== "undefined" && !audioWarmerInstalled) {
  audioWarmerInstalled = true;
  window.addEventListener("pointerdown", warmAudioOnGesture);
  window.addEventListener("keydown", warmAudioOnGesture);
}

// Returns the shared AudioContext, attempting to resume it if suspended. Best
// effort — if the warmer never fired (no gesture yet) the context may stay
// suspended and the first beep is silent; subsequent beeps work once any
// gesture resumes it.
function getThinkingAudioContext(): AudioContext | null {
  if (!sharedAudioCtx) {
    sharedAudioCtx = createAudioContext();
  }
  const ctx = sharedAudioCtx;
  if (ctx && ctx.state === "suspended") {
    ctx
      .resume()
      .catch((err: unknown) =>
        logError("[tuntun:thinking] resume failed:", err)
      );
  }
  return ctx;
}

function ThinkingIndicator() {
  const room = useRoomContext();
  const { localParticipant } = useLocalParticipant();
  const thinkingRef = useRef(false);
  const beepTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const stopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const noteIndexRef = useRef(0);

  useEffect(() => {
    const playBeep = (ctx: AudioContext, freq: number) => {
      const now = ctx.currentTime;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      // Sine = softest waveform; smooth envelope = no clicks.
      osc.type = "sine";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0, now);
      gain.gain.linearRampToValueAtTime(THINKING_PEAK_GAIN, now + 0.12);
      gain.gain.linearRampToValueAtTime(THINKING_PEAK_GAIN, now + 0.35);
      gain.gain.linearRampToValueAtTime(0, now + 0.7);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.72);
    };

    const stopThinking = () => {
      thinkingRef.current = false;
      if (beepTimerRef.current !== null) {
        clearInterval(beepTimerRef.current);
        beepTimerRef.current = null;
      }
      if (stopTimerRef.current !== null) {
        clearTimeout(stopTimerRef.current);
        stopTimerRef.current = null;
      }
    };

    // Pick the next soft note, cycling through the consonant interval.
    const noteFreq = (i: number) =>
      THINKING_FREQS[i % THINKING_FREQS.length] ?? THINKING_FREQS[0] ?? 523.25;

    const startThinking = () => {
      if (thinkingRef.current) {
        // Already thinking — refresh the safety auto-stop window.
        if (stopTimerRef.current !== null) {
          clearTimeout(stopTimerRef.current);
        }
        stopTimerRef.current = setTimeout(stopThinking, THINKING_MAX_MS);
        return;
      }
      const ctx = getThinkingAudioContext();
      if (!ctx) {
        logError("ThinkingIndicator — no AudioContext, beeps disabled");
        return;
      }
      if (ctx.state !== "running") {
        log(
          "ThinkingIndicator — audio not running yet (state:",
          ctx.state,
          ") — tap the screen once to enable the thinking sound"
        );
      }
      thinkingRef.current = true;
      // One soft beep immediately, then on a slow comforting cadence.
      playBeep(ctx, noteFreq(noteIndexRef.current));
      noteIndexRef.current += 1;
      beepTimerRef.current = setInterval(() => {
        if (!thinkingRef.current) {
          return;
        }
        const tickCtx = getThinkingAudioContext();
        if (tickCtx) {
          playBeep(tickCtx, noteFreq(noteIndexRef.current));
        }
        noteIndexRef.current += 1;
      }, THINKING_INTERVAL_MS);
      stopTimerRef.current = setTimeout(stopThinking, THINKING_MAX_MS);
      log("ThinkingIndicator — agent thinking, soft tone started");
    };

    const localIdentity = localParticipant?.identity;
    const isAgent = (identity?: string) => identity?.startsWith("agent");

    const onTranscriptionReceived = (
      segments: unknown,
      participant: unknown
    ) => {
      const p = participant as { identity?: string };
      const segs = segments as Array<{ final?: boolean }>;
      if (p?.identity === localIdentity && segs?.some((s) => s.final)) {
        startThinking();
      } else if (isAgent(p?.identity)) {
        if (thinkingRef.current) {
          log("ThinkingIndicator — agent replying, tone stopped");
        }
        stopThinking();
      }
    };

    const onActiveSpeakersChanged = (speakers: unknown) => {
      const list = speakers as Array<{ identity?: string }>;
      if (list.some((s) => isAgent(s.identity))) {
        stopThinking();
      }
    };

    room.on(RoomEvent.TranscriptionReceived, onTranscriptionReceived);
    room.on(RoomEvent.ActiveSpeakersChanged, onActiveSpeakersChanged);

    return () => {
      room.off(RoomEvent.TranscriptionReceived, onTranscriptionReceived);
      room.off(RoomEvent.ActiveSpeakersChanged, onActiveSpeakersChanged);
      stopThinking();
    };
  }, [room, localParticipant]);

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
  // useDisconnectButton ships its own className; pull it out of the spread
  // and merge with our control-dock styling instead of overwriting.
  const { buttonProps: disconnectButtonPropsRaw } = useDisconnectButton({});
  const { className: disconnectButtonClassName, ...disconnectButtonProps } =
    disconnectButtonPropsRaw;
  const disconnectClassName = cn(
    disconnectButtonClassName,
    "size-12 rounded-full [&_svg]:size-5"
  );

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
    <div className="relative h-full w-full overflow-hidden bg-black">
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
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-4">
          <div className="flex size-20 items-center justify-center rounded-full border border-white/10 bg-white/5 backdrop-blur-sm">
            <VideoOff className="size-9 text-white/60" />
          </div>
          <p className="text-sm text-white/60">Camera is off</p>
        </div>
      )}

      {/* Top status bar — live indicator + rear-camera badge */}
      <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-between gap-3 bg-gradient-to-b from-black/60 to-transparent p-4 pt-5">
        <div className="flex items-center gap-2 rounded-full border border-white/10 bg-black/40 px-3 py-1.5 backdrop-blur-md">
          <span className="relative flex size-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
          </span>
          <span className="font-medium text-sm text-white">Reflex active</span>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-black/40 px-3 py-1.5 font-medium text-white/80 text-xs backdrop-blur-md">
          <Camera className="size-3.5" />
          Rear camera
        </span>
      </div>

      {/* Bottom control dock — frosted, larger touch targets */}
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

          <Button
            aria-label={isCameraEnabled ? "Turn camera off" : "Turn camera on"}
            className="size-12 rounded-xl [&_svg]:size-5"
            type="button"
            variant={isCameraEnabled ? "default" : "destructive"}
            {...camButtonProps}
          >
            {isCameraEnabled ? <Video /> : <VideoOff />}
          </Button>

          <div className="mx-1 h-8 w-px bg-white/10" />

          <Button
            aria-label="End reflex session"
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

/**
 * Force the microphone and rear camera ON once the room connects, so the
 * Reflex AI always starts with a live audio + video feed regardless of the
 * PreJoin toggle state. Runs exactly once per connection — after that the user
 * may still toggle freely via the control dock in LocalCameraPreview.
 *
 * Why: the `audio`/`video` props on <LiveKitRoom> only set the *initial*
 * publish intent. If a toggle lands off (or the initial publish races), the
 * agent could start without media. This is a safety net that guarantees both
 * tracks are published before the session is considered live.
 */
function ForceMediaOn() {
  const { localParticipant } = useLocalParticipant();
  const didEnable = useRef(false);

  // localParticipant.sid is populated once the room has actually connected
  // and the participant is registered, so it's a reliable "connected" signal
  // without wiring an extra RoomEvent listener.
  useEffect(() => {
    if (didEnable.current || !localParticipant.sid) {
      return;
    }
    didEnable.current = true;

    const enable = async () => {
      try {
        await localParticipant.setMicrophoneEnabled(true);
        log("ForceMediaOn: microphone enabled");
      } catch (err) {
        logError("ForceMediaOn: microphone enable failed:", err);
      }
      try {
        // Pass the rear-camera capture options so re-enabling keeps the
        // environment-facing camera, not the default selfie cam.
        await localParticipant.setCameraEnabled(true, REAR_CAMERA_CAPTURE);
        log("ForceMediaOn: rear camera enabled");
      } catch (err) {
        logError("ForceMediaOn: rear camera enable failed:", err);
      }
    };

    enable().catch((err) => logError("ForceMediaOn: unexpected failure:", err));
  }, [localParticipant]);

  return null;
}

export function ReflexCall() {
  const router = useRouter();
  const [tokenResponse, setTokenResponse] = useState<TokenResponse | null>(
    null
  );
  // ponytail: Overwatch is auto-active for the blind user's whole Reflex
  // session — the Reflex room IS the Overwatch room, so the guardian (and the
  // agent's spectator-link minter) can spectate the live chest camera at any
  // time without a manual start. Ended on disconnect.
  const startOverwatch = useMutation(api.overwatch.startSession);
  const endOverwatch = useMutation(api.overwatch.endSession);
  const overwatchSessionId = useRef<string | null>(null);

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

    // Auto-start Overwatch against this Reflex room. Best-effort: a failure
    // here must not block the call — the agent/guardian just won't see an
    // active session row.
    try {
      const id = await startOverwatch({ livekitRoomName: roomName });
      overwatchSessionId.current = id as string;
      log("Overwatch auto-started — sessionId:", id, "room:", roomName);
    } catch (err) {
      logError("Overwatch auto-start failed (non-blocking):", err);
    }
  };

  const handleDisconnected = () => {
    const id = overwatchSessionId.current;
    overwatchSessionId.current = null;
    if (id) {
      endOverwatch({ sessionId: id as never })
        .then(() => log("Overwatch session ended — sessionId:", id))
        .catch((err: unknown) =>
          logError("Overwatch end failed (non-blocking):", err)
        );
    }
    router.push("/dashboard/reflex");
  };

  if (!tokenResponse) {
    return (
      <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background p-4">
        {/* Background — subtle radial, matches landing hero */}
        <div
          aria-hidden
          className="absolute inset-0 -z-10 [background:radial-gradient(125%_125%_at_50%_100%,transparent_0%,var(--color-background)_75%)]"
        />
        <div
          aria-hidden
          className="absolute inset-0 -z-20 hidden opacity-60 lg:block"
        >
          <div className="absolute top-0 left-0 h-[320rem] w-[140rem] -translate-y-[87.5%] -rotate-45 rounded-full bg-[radial-gradient(68.54%_68.72%_at_55.02%_31.46%,hsla(260,80%,85%,0.08)_0,hsla(260,40%,55%,0.02)_50%,transparent_80%)]" />
        </div>

        <div className="w-full max-w-md">
          <Link
            className="mb-6 inline-flex items-center gap-1.5 text-muted-foreground text-sm transition-colors hover:text-foreground"
            href="/dashboard/reflex"
          >
            <ArrowLeft className="size-4" />
            Back to Reflex
          </Link>

          {/* Brand header */}
          <div className="mb-7 flex flex-col items-center text-center">
            <div className="flex size-14 items-center justify-center rounded-2xl border bg-muted shadow-sm">
              <ScanEye className="size-7 text-primary" />
            </div>
            <h1 className="mt-5 font-semibold text-2xl tracking-tight">
              Reflex AI Session
            </h1>
            <p className="mt-2 max-w-xs text-balance text-muted-foreground text-sm">
              Real-time vision-to-audio obstacle detection. Tutu watches your
              camera and warns you about hazards instantly.
            </p>
          </div>

          {/* PreJoin panel */}
          <div className="overflow-hidden rounded-2xl border bg-card shadow-lg ring-1 ring-background">
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

          {/* What to expect */}
          <ul className="mt-6 flex flex-col gap-2.5">
            {[
              { icon: Camera, text: "Uses your back camera by default" },
              { icon: Mic, text: "Microphone listens for voice commands" },
              { icon: MapPin, text: "Shares live location for navigation" },
            ].map(({ icon: Icon, text }) => (
              <li
                className="flex items-center gap-3 rounded-lg border bg-card/60 px-3 py-2.5 text-muted-foreground text-sm"
                key={text}
              >
                <Icon className="size-4 shrink-0 text-primary" />
                <span>{text}</span>
              </li>
            ))}
          </ul>
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
        video={REAR_CAMERA_CAPTURE}
      >
        <ForceMediaOn />
        <RoomEventLogger />
        <GpsPublisher />
        <ProfilePublisher />
        <ThinkingIndicator />
        <LocalCameraPreview />
        <RoomAudioRenderer />
      </LiveKitRoom>
    </div>
  );
}

export default ReflexCall;
