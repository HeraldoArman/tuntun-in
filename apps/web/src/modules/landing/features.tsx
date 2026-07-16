import { Card, CardContent, CardHeader } from "@tuntun-in/ui/components/card";
import { Eye, MapPinned, ScanLine, ShieldAlert, Users } from "lucide-react";
import type { ReactNode } from "react";
import { Mascot } from "@/modules/landing/mascot";

const features = [
  {
    icon: Eye,
    title: "Reflex AI",
    description:
      "Real-time vision-to-audio. AI scans chest camera video and instantly detects typical Indonesian street obstacles with instant spatial audio warnings.",
  },
  {
    icon: MapPinned,
    title: "Deep Navigator",
    description:
      'Macro-to-micro navigation. Aligns Google Maps with visual capture — "Turn left right after passing the blue food cart ahead."',
  },
  {
    icon: ScanLine,
    title: "Transit Spotter",
    description:
      "Contextual OCR. Aggressive scanning mode reads and announces bus corridor numbers or angkot routes stopping near the user.",
  },
  {
    icon: ShieldAlert,
    title: "Overwatch Mode",
    description:
      "Emergency spectator. On critical danger, sends a secret WebRTC link via WhatsApp to family so they can view the camera live and guide verbally.",
  },
  {
    icon: Users,
    title: "Live Crowdsourced Mapping",
    description:
      "Automatic reporting of damaged road/sidewalk GPS to a public web dashboard. Captures images and coordinates silently, without manual intervention.",
  },
] as const;

const CardDecorator = ({ children }: { children: ReactNode }) => (
  <div className="mask-radial-from-40% mask-radial-to-60% relative mx-auto size-36 duration-200 [--color-border:color-mix(in_oklab,var(--color-zinc-950)_10%,transparent)] group-hover:[--color-border:color-mix(in_oklab,var(--color-zinc-950)_20%,transparent)] dark:[--color-border:color-mix(in_oklab,var(--color-white)_15%,transparent)] dark:group-hover:[--color-border:color-mix(in_oklab,var(--color-white)_20%,transparent)]">
    <div
      aria-hidden
      className="absolute inset-0 bg-[linear-gradient(to_right,var(--color-border)_1px,transparent_1px),linear-gradient(to_bottom,var(--color-border)_1px,transparent_1px)] bg-[size:24px_24px] dark:opacity-50"
    />
    <div className="absolute inset-0 m-auto flex size-12 items-center justify-center border-t border-l bg-background">
      {children}
    </div>
  </div>
);

export function Features() {
  return (
    <section
      aria-labelledby="features-heading"
      className="relative overflow-hidden bg-muted/30 py-16 md:py-32"
      id="features"
    >
      {/* Decorative mascot — floating top-right above the feature cards */}
      <Mascot
        className="absolute top-8 right-4 z-0 hidden h-40 w-40 rotate-12 drop-shadow-2xl sm:right-10 md:block lg:h-56 lg:w-56"
        name="robot_05"
      />
      <div className="@container relative z-10 mx-auto max-w-5xl px-6">
        <div className="text-center">
          <h2
            className="text-balance font-semibold text-4xl lg:text-5xl"
            id="features-heading"
          >
            Built to cover your needs
          </h2>
          <p className="mt-4 text-muted-foreground">
            Five core features that replace expensive hardware with AI-powered
            software on a phone you already own.
          </p>
        </div>
        <div className="mx-auto mt-8 flex max-w-5xl flex-wrap justify-center gap-6 md:mt-16">
          {features.map(({ icon: Icon, title, description }) => (
            <Card
              className="group w-full max-w-sm shadow-zinc-950/5 sm:w-[calc(50%-0.75rem)] lg:w-[calc(33.333%-1rem)]"
              key={title}
            >
              <CardHeader className="pb-3">
                <CardDecorator>
                  <Icon aria-hidden className="size-6" />
                </CardDecorator>
                <h3 className="mt-6 font-medium">{title}</h3>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground text-sm">{description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
}
