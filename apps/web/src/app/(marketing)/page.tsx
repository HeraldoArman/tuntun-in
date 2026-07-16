import { Architecture } from "@/modules/landing/architecture";
import { Audience } from "@/modules/landing/audience";
import { ContentSection } from "@/modules/landing/content-section";
import { CostComparison } from "@/modules/landing/cost-comparison";
import { Features } from "@/modules/landing/features";
import { FinalCTA } from "@/modules/landing/final-cta";
import { Hero } from "@/modules/landing/hero";
import { Problem } from "@/modules/landing/problem";

export default function Home() {
  return (
    <>
      <Hero />
      <Problem />
      <ContentSection />
      <Architecture />
      <Features />
      <CostComparison />
      <Audience />
      <FinalCTA />
    </>
  );
}
