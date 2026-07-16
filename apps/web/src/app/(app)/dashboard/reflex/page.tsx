import { Button } from "@tuntun-in/ui/components/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@tuntun-in/ui/components/card";
import { ScanEyeIcon } from "lucide-react";
import Link from "next/link";

export default function ReflexPage() {
  return (
    <div className="p-6">
      <div className="mb-8">
        <h1 className="font-semibold text-2xl">Reflex AI</h1>
        <p className="mt-1 text-muted-foreground text-sm">
          Real-time vision-to-audio obstacle detection powered by Gemini Live.
        </p>
      </div>

      <div className="max-w-2xl">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <ScanEyeIcon className="size-5" />
              Start a Reflex Session
            </CardTitle>
            <CardDescription>
              Launch a full-screen video call with the Tuntun agent. Your camera
              and microphone will be streamed in real time for instant obstacle
              detection and spatial audio warnings.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild size="lg">
              <Link href="/reflex">
                <ScanEyeIcon className="size-4" />
                Start Session
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
