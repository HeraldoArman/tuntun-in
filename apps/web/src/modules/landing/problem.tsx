import { Card, CardContent, CardHeader } from "@tuntun-in/ui/components/card";
import { Construction, EyeOff, MapPin, Navigation, Wallet } from "lucide-react";
import type { ReactNode } from "react";

const problems = [
  {
    icon: Construction,
    title: "Inadequate Infrastructure",
    description:
      "Guiding blocks are often disconnected, damaged, blocked by utility poles, or covered by street vendors' carts.",
  },
  {
    icon: EyeOff,
    title: "White Cane Limits",
    description:
      "Standard cane sweeps cannot detect waist-high or head-high obstacles like banners, tree branches, truck beds, or road barriers.",
  },
  {
    icon: MapPin,
    title: "The Last Meter Problem",
    description:
      "GPS inaccuracies of 3-5 meters are highly dangerous for the visually impaired when trying to find specific safe route points.",
  },
  {
    icon: Navigation,
    title: "Public Transport Barriers",
    description:
      "Inability to see the corridor numbers of TransJakarta buses or public minivans (angkot) stopping nearby.",
  },
  {
    icon: Wallet,
    title: "Financial Accessibility",
    description:
      "Smart wearable solutions from abroad are too expensive for the majority of the population in developing countries.",
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

export function Problem() {
  return (
    <section className="bg-muted/30 py-16 md:py-32">
      <div className="mx-auto max-w-5xl px-6">
        <div className="text-center">
          <h2
            className="text-balance font-semibold text-4xl lg:text-5xl"
            id="problem-heading"
          >
            The mobility gap
          </h2>
          <p className="mt-4 text-muted-foreground">
            Pedestrian infrastructure in Indonesia remains highly challenging
            for the visually impaired.
          </p>
        </div>
        <div className="mx-auto mt-8 flex max-w-5xl flex-wrap justify-center gap-6 md:mt-16">
          {problems.map(({ icon: Icon, title, description }) => (
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
