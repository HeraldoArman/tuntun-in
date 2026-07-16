import { Button } from "@tuntun-in/ui/components/button";
import Link from "next/link";

export function FinalCTA() {
  return (
    <section aria-label="Get started" className="py-16 md:py-32">
      <div className="mx-auto max-w-5xl px-6">
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
