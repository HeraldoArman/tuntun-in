import { cn } from "@tuntun-in/ui/lib/utils";
import { Eye, ShieldCheck } from "lucide-react";

export function ContentSection() {
  return (
    <section>
      <div className="bg-muted/50 py-24">
        <div className="mx-auto w-full max-w-5xl px-6">
          <div>
            <span className="text-primary">How it works</span>
            <h2 className="mt-4 font-semibold text-4xl text-foreground">
              A phone becomes smart eyes
            </h2>
            <p className="mt-4 mb-12 text-lg text-muted-foreground">
              A chest-mounted phone streams video to Gemini Live AI, which
              interprets obstacles in real time and speaks spatial audio
              warnings. No extra hardware needed.
            </p>
          </div>

          <div className="space-y-6 border-foreground/5 [--color-border:color-mix(in_oklab,var(--color-foreground)10%,transparent)] sm:space-y-0 sm:divide-y">
            <div className="grid sm:grid-cols-5 sm:divide-x">
              <PipelineIllustration className="sm:col-span-2" />
              <div className="mt-6 sm:col-span-3 sm:mt-0 sm:border-l sm:pl-12">
                <h3 className="font-semibold text-foreground text-xl">
                  Real-time AI pipeline
                </h3>
                <p className="mt-4 text-lg text-muted-foreground">
                  Camera feed reaches Gemini Live with sub-second latency. The
                  AI identifies obstacles — parked motorcycles, open manholes,
                  uneven pavement — and issues spatial audio warnings through
                  the phone speaker or earphones.
                </p>
              </div>
            </div>
            <div className="grid sm:grid-cols-5 sm:divide-x">
              <div className="pt-12 sm:col-span-3 sm:border-r sm:pr-12">
                <h3 className="font-semibold text-foreground text-xl">
                  Multi-layer safety net
                </h3>
                <p className="mt-4 text-lg text-muted-foreground">
                  Reflex AI handles instant obstacle warnings. For complex
                  situations, DeepAgents reasoning kicks in. If critical danger
                  is detected, Overwatch mode sends a live video link to family
                  via WhatsApp.
                </p>
              </div>
              <div className="row-start-1 flex items-center justify-center pt-12 sm:col-span-2 sm:row-start-auto">
                <SafetyIllustration className="pt-8" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

interface IllustrationProps {
  className?: string;
}

export const PipelineIllustration = ({ className }: IllustrationProps) => (
  <div
    className={cn(
      "[mask-image:radial-gradient(ellipse_50%_50%_at_50%_50%,#000_50%,transparent_100%)]",
      className
    )}
  >
    <ul className="mx-auto w-fit font-medium font-mono text-2xl text-muted-foreground">
      {["Capture", "Stream", "Analyze", "Warn", "Navigate"].map(
        (item, index) => (
          <li
            className={cn(
              index === 2 &&
                "relative text-foreground before:absolute before:-translate-x-[110%] before:text-orange-500 before:content-['AI']"
            )}
            key={item}
          >
            {item}
          </li>
        )
      )}
    </ul>
  </div>
);

export const SafetyIllustration = ({ className }: IllustrationProps) => (
  <div className={cn("relative", className)}>
    <div className="absolute flex -translate-x-1/2 -translate-y-[110%] items-center gap-2 rounded-lg bg-background p-1 shadow-black-950/10 shadow-lg">
      <div className="flex size-7 items-center justify-center rounded-sm bg-emerald-500/10">
        <ShieldCheck className="size-4 text-emerald-500" />
      </div>
      <span className="font-medium text-sm">Overwatch Active</span>
    </div>
    <div className="flex items-center gap-3 rounded-xl border bg-background p-4">
      <div className="flex size-12 items-center justify-center rounded-lg bg-muted">
        <Eye className="size-6 text-muted-foreground" />
      </div>
      <div>
        <p className="font-medium text-sm">Live Feed</p>
        <p className="text-muted-foreground text-xs">
          Shared with emergency contact
        </p>
      </div>
    </div>
  </div>
);
