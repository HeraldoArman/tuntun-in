import { Card, CardContent, CardHeader } from "@tuntun-in/ui/components/card";
import { Building2, Eye, Heart } from "lucide-react";
import type { ReactNode } from "react";

const audiences = [
  {
    icon: Eye,
    title: "Primary Users",
    description:
      "Fully blind or low vision individuals who rely on a white cane for daily mobility.",
  },
  {
    icon: Heart,
    title: "Families & Guardians",
    description:
      "Assurance of mobility safety through Overwatch mode live oversight and emergency takeover.",
  },
  {
    icon: Building2,
    title: "Local Governments",
    description:
      "Crowdsourced infrastructure maps for urban planning and sidewalk maintenance prioritization.",
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

export function Audience() {
  return (
    <section
      aria-labelledby="audience-heading"
      className="bg-muted/30 py-16 md:py-32"
    >
      <div className="@container mx-auto max-w-5xl px-6">
        <div className="text-center">
          <h2
            className="text-balance font-semibold text-4xl lg:text-5xl"
            id="audience-heading"
          >
            Built for
          </h2>
          <p className="mt-4 text-muted-foreground">
            Three groups benefit from one unified platform.
          </p>
        </div>
        <div className="mx-auto mt-8 grid @min-4xl:max-w-full max-w-sm @min-4xl:grid-cols-3 gap-6 *:text-center md:mt-16">
          {audiences.map(({ icon: Icon, title, description }) => (
            <Card className="group shadow-zinc-950/5" key={title}>
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
