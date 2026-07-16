import { Badge } from "@tuntun-in/ui/components/badge";
import { Card, CardContent, CardHeader } from "@tuntun-in/ui/components/card";
import { Brain, Zap } from "lucide-react";
import type { ReactNode } from "react";

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

export function Architecture() {
  return (
    <section
      aria-labelledby="architecture-heading"
      className="py-16 md:py-32"
      id="how-it-works"
    >
      <div className="@container mx-auto max-w-5xl px-6">
        <div className="text-center">
          <h2
            className="text-balance font-semibold text-4xl lg:text-5xl"
            id="architecture-heading"
          >
            Dual-brain AI architecture
          </h2>
          <p className="mt-4 text-muted-foreground">
            Two AI brains work together — instant reflex reactions for safety,
            deep reasoning for navigation.
          </p>
        </div>
        <div className="mx-auto mt-8 grid @min-4xl:max-w-full max-w-sm @min-4xl:grid-cols-2 gap-6 *:text-center md:mt-16">
          <Card className="group shadow-zinc-950/5">
            <CardHeader className="pb-3">
              <CardDecorator>
                <Zap aria-hidden className="size-6" />
              </CardDecorator>
              <Badge className="mx-auto mt-6 w-fit" variant="default">
                Brain 1 — Reflex
              </Badge>
              <h3 className="mt-3 font-medium">Gemini Live</h3>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground text-sm">
                Real-time vision-to-audio with sub-second latency. Scans
                chest-mounted camera video for Indonesian street obstacles —
                parked motorcycles, open manholes — with instant spatial audio
                warnings.
              </p>
            </CardContent>
          </Card>
          <Card className="group shadow-zinc-950/5">
            <CardHeader className="pb-3">
              <CardDecorator>
                <Brain aria-hidden className="size-6" />
              </CardDecorator>
              <Badge className="mx-auto mt-6 w-fit" variant="secondary">
                Brain 2 — Reasoning
              </Badge>
              <h3 className="mt-3 font-medium">DeepAgents</h3>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground text-sm">
                LangChain DeepAgents for multi-step route orchestration. Aligns
                macro GPS data with micro visual understanding for
                landmark-based instructions.
              </p>
            </CardContent>
          </Card>
        </div>
        <div className="mx-auto mt-6 max-w-5xl">
          <Card className="border-dashed">
            <CardContent className="flex items-center gap-3 py-4">
              <Badge variant="outline">Handoff</Badge>
              <p className="text-muted-foreground text-sm">
                <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                  session.update_agent()
                </code>{" "}
                switches between brains mid-session.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </section>
  );
}
