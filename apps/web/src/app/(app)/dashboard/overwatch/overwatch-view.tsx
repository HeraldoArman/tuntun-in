"use client";

import { api } from "@tuntun-in/backend/convex/_generated/api";
import { Badge } from "@tuntun-in/ui/components/badge";
import { Button } from "@tuntun-in/ui/components/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@tuntun-in/ui/components/card";
import { useMutation, useQuery } from "convex/react";
import { EyeIcon, ShieldAlertIcon, ShieldIcon } from "lucide-react";
import { toast } from "sonner";

function renderGuardianList(
  guardians:
    | {
        _id: string;
        fullName: string;
        email?: string;
      }[]
    | undefined
) {
  if (guardians === undefined) {
    return <p className="text-muted-foreground text-sm">Loading...</p>;
  }
  if (guardians.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        No guardian linked yet. Ask a family member to register as a guardian
        and add you by email.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-3">
      {guardians.map((guardian) => (
        <li
          className="flex items-center justify-between rounded-lg border p-3"
          key={guardian._id}
        >
          <div className="flex flex-col gap-0.5">
            <span className="font-medium text-sm">{guardian.fullName}</span>
            {guardian.email && (
              <span className="text-muted-foreground text-xs">
                {guardian.email}
              </span>
            )}
          </div>
          <Badge variant="default">Guardian</Badge>
        </li>
      ))}
    </ul>
  );
}

function renderActiveSession(
  activeSession:
    | {
        _id: string;
        livekitRoomName: string;
        status: string;
        startedAt: number;
      }
    | null
    | undefined,
  onStartDemo: () => void,
  onEnd: (sessionId: string) => void
) {
  if (activeSession === undefined) {
    return <p className="text-muted-foreground text-sm">Loading...</p>;
  }
  if (activeSession === null) {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-muted-foreground text-sm">
          No active Overwatch session. You can start a demo session below.
        </p>
        <Button className="w-fit" onClick={onStartDemo} variant="destructive">
          <ShieldAlertIcon className="size-4" />
          Start Overwatch (Demo)
        </Button>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between rounded-lg border border-destructive/30 bg-destructive/5 p-3">
        <div className="flex flex-col gap-0.5">
          <span className="font-medium text-sm">Session is live</span>
          <span className="text-muted-foreground text-xs">
            Room: {activeSession.livekitRoomName}
          </span>
          <span className="text-muted-foreground text-xs">
            Started {new Date(activeSession.startedAt).toLocaleTimeString()}
          </span>
        </div>
        <Badge variant="destructive">Active</Badge>
      </div>
      <Button
        className="w-fit"
        onClick={() => onEnd(activeSession._id)}
        variant="outline"
      >
        End Session
      </Button>
    </div>
  );
}

export function OverwatchView() {
  const guardians = useQuery(api.guardianLinks.getMyGuardians);
  const activeSession = useQuery(api.overwatch.getMyActiveSession);
  const startSession = useMutation(api.overwatch.startSession);
  const endSession = useMutation(api.overwatch.endSession);

  const handleStartDemo = async () => {
    try {
      const roomName = `overwatch-${Date.now()}`;
      await startSession({ livekitRoomName: roomName });
      toast.success("Overwatch session started");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Failed to start session"
      );
    }
  };

  const handleEnd = async (sessionId: string) => {
    try {
      await endSession({ sessionId: sessionId as never });
      toast.success("Overwatch session ended");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Failed to end session"
      );
    }
  };

  return (
    <div className="p-6">
      <div className="mb-8">
        <h1 className="font-semibold text-2xl">Overwatch</h1>
        <p className="mt-1 text-muted-foreground text-sm">
          Emergency spectator mode. When triggered, your guardian can view your
          camera live and guide you verbally.
        </p>
      </div>

      <div className="flex max-w-2xl flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <ShieldIcon className="size-5" />
              Your Guardians
            </CardTitle>
            <CardDescription>
              These are the family members who can receive your Overwatch
              alerts.
            </CardDescription>
          </CardHeader>
          <CardContent>{renderGuardianList(guardians)}</CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <EyeIcon className="size-5" />
              Active Overwatch Session
            </CardTitle>
            <CardDescription>
              When an Overwatch session is active, your guardian can see your
              camera feed in real time.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {renderActiveSession(activeSession, handleStartDemo, handleEnd)}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
