import { Button } from "@tuntun-in/ui/components/button";
import Link from "next/link";
import { Mascot } from "@/modules/landing/mascot";

export function FinalCTA() {
  return (
    <section
      aria-label="Get started"
      className="relative overflow-hidden py-16 md:py-32"
    >
      {/* Decorative mascot — anchored top-right as a friendly closing cameo */}
      <Mascot
        className="absolute top-8 right-6 z-0 hidden h-40 w-40 rotate-6 drop-shadow-2xl md:right-16 lg:block lg:h-64 lg:w-64"
        name="robot_02"
      />
      <div className="relative z-10 mx-auto max-w-5xl px-6">
        <div className="text-center">
          <h2 className="text-balance font-semibold text-4xl lg:text-5xl">
            Start your journey
          </h2>
          <p className="mt-4 text-muted-foreground">
            No extra hardware required. Just your smartphone and a standard
            cane.
          </p>
          <div className="mt-12 flex flex-wrap justify-center gap-4">
            <Button asChild size="lg">
              <Link href="/register">
                <span>Get Started</span>
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link href="/dashboard">
                <span>Try the Agent</span>
              </Link>
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
