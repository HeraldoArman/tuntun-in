import { Button } from "@tuntun-in/ui/components/button";
import { Cpu, Sparkles } from "lucide-react";
import Link from "next/link";
import { Mascot } from "@/modules/landing/mascot";

const tableData = [
  {
    feature: "Real-time obstacle detection",
    imported: false,
    tuntun: true,
  },
  {
    feature: "Voice navigation",
    imported: false,
    tuntun: true,
  },
  {
    feature: "Crowdsourced mapping",
    imported: false,
    tuntun: true,
  },
  {
    feature: "Cost",
    imported: "$600 – $4,000 USD",
    tuntun: "~$8.5 USD + phone",
  },
  {
    feature: "Extra hardware",
    imported: "Smart cane or glasses",
    tuntun: "Chest mount + standard cane",
  },
  {
    feature: "Emergency oversight",
    imported: "Not included",
    tuntun: "Live WebRTC link via WhatsApp",
  },
];

export function CostComparison() {
  return (
    <section
      aria-labelledby="cost-heading"
      className="relative overflow-hidden py-16 md:py-32"
    >
      {/* Decorative mascot — peeking from the bottom-left near the table */}
      <Mascot
        className="absolute bottom-16 left-4 z-0 hidden h-40 w-40 rotate-6 drop-shadow-2xl sm:left-10 md:block lg:h-64 lg:w-64"
        name="robot_09"
      />
      <div className="relative z-10 mx-auto max-w-5xl px-6">
        <div className="mx-auto mb-12 max-w-3xl text-center">
          <h2
            className="text-balance font-semibold text-4xl lg:text-5xl"
            id="cost-heading"
          >
            Affordable by design
          </h2>
          <p className="mt-4 text-muted-foreground">
            No expensive imported hardware. Just a phone chest mount, a standard
            cane, and the smartphone you already carry.
          </p>
        </div>
        <div className="w-full overflow-auto lg:overflow-visible">
          <table className="w-[200vw] border-separate border-spacing-x-3 md:w-full dark:[--color-muted:var(--color-zinc-900)]">
            <thead className="sticky top-0 bg-background">
              <tr className="*:py-4 *:text-left *:font-medium">
                <th className="lg:w-2/5" />
                <th className="space-y-3">
                  <span className="block">Imported Devices</span>
                  <Button asChild size="sm" variant="outline">
                    <Link href="#">Learn more</Link>
                  </Button>
                </th>
                <th className="space-y-3 rounded-t-(--radius) bg-muted px-4">
                  <span className="block">Tuntun.In</span>
                  <Button asChild size="sm">
                    <Link href="/register">Get Started</Link>
                  </Button>
                </th>
              </tr>
            </thead>
            <tbody className="text-sm">
              <tr className="*:py-3">
                <td className="flex items-center gap-2 font-medium text-muted-foreground">
                  <Cpu className="size-4" />
                  <span>Features</span>
                </td>
                <td />
                <td className="border-none bg-muted px-4" />
              </tr>
              {tableData.slice(0, 3).map((row, index) => (
                <tr className="*:border-b *:py-3" key={index}>
                  <td className="text-muted-foreground">{row.feature}</td>
                  <td>
                    {row.imported === false ? (
                      <span className="text-muted-foreground">&mdash;</span>
                    ) : (
                      row.imported
                    )}
                  </td>
                  <td className="border-none bg-muted px-4">
                    <div className="-mb-3 border-b py-3">
                      {row.tuntun === true ? (
                        <svg
                          aria-label="Included"
                          className="size-4"
                          fill="currentColor"
                          role="img"
                          viewBox="0 0 24 24"
                          xmlns="http://www.w3.org/2000/svg"
                        >
                          <path
                            clipRule="evenodd"
                            d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12Zm13.36-1.814a.75.75 0 1 0-1.22-.872l-3.236 4.53L9.53 12.22a.75.75 0 0 0-1.06 1.06l2.25 2.25a.75.75 0 0 0 1.14-.094l3.75-5.25Z"
                            fillRule="evenodd"
                          />
                        </svg>
                      ) : (
                        row.tuntun
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              <tr className="*:pt-8 *:pb-3">
                <td className="flex items-center gap-2 font-medium text-muted-foreground">
                  <Sparkles className="size-4" />
                  <span>Cost & Hardware</span>
                </td>
                <td />
                <td className="border-none bg-muted px-4" />
              </tr>
              {tableData.slice(3).map((row, index) => (
                <tr className="*:border-b *:py-3" key={index}>
                  <td className="text-muted-foreground">{row.feature}</td>
                  <td>{row.imported}</td>
                  <td className="border-none bg-muted px-4">
                    <div className="-mb-3 border-b py-3">{row.tuntun}</div>
                  </td>
                </tr>
              ))}
              <tr className="*:py-6">
                <td />
                <td />
                <td className="rounded-b-(--radius) border-none bg-muted px-4" />
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
