"use client";

import { Button } from "@tuntun-in/ui/components/button";
import { ArrowRight, ChevronRight } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { siConvex, siGooglegemini, siLivekit, siNextdotjs } from "simple-icons";
import { Mascot } from "@/modules/landing/mascot";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.08, delayChildren: 0.1 },
  },
} as const;

const itemVariants = {
  hidden: { opacity: 0, y: 20, filter: "blur(12px)" },
  visible: {
    opacity: 1,
    y: 0,
    filter: "blur(0px)",
    transition: { type: "spring" as const, bounce: 0.3, duration: 1.5 },
  },
} as const;

export function Hero() {
  const reduce = useReducedMotion();

  return (
    <section aria-label="Hero" className="relative overflow-hidden">
      {/* Background gradient — subtle radial, adapts to light/dark tokens */}
      <div
        aria-hidden
        className="absolute inset-0 -z-10 [background:radial-gradient(125%_125%_at_50%_100%,transparent_0%,var(--color-background)_75%)]"
      />
      <div
        aria-hidden
        className="absolute inset-0 -z-20 hidden opacity-60 lg:block"
      >
        <div className="absolute top-0 left-0 h-[320rem] w-[140rem] -translate-y-[87.5%] -rotate-45 rounded-full bg-[radial-gradient(68.54%_68.72%_at_55.02%_31.46%,hsla(260,80%,85%,0.08)_0,hsla(260,40%,55%,0.02)_50%,transparent_80%)]" />
      </div>

      {/* Decorative mascot — top-left, peeks behind the hero copy on wide screens */}
      <Mascot
        className="absolute top-24 left-4 z-0 hidden h-48 w-48 -rotate-12 drop-shadow-2xl md:left-10 lg:block lg:h-72 lg:w-72"
        name="robot_07"
      />
      {/* Decorative mascot — bottom-right, anchors near the mockup */}
      <Mascot
        className="absolute top-1/2 right-4 z-0 hidden h-40 w-40 translate-y-8 rotate-12 drop-shadow-2xl md:right-10 lg:block lg:h-64 lg:w-64"
        name="robot_03"
      />

      <div className="relative z-10 mx-auto max-w-7xl px-6 pt-24 md:pt-36">
        <div className="text-center sm:mx-auto lg:mt-0 lg:mr-auto">
          <motion.div
            animate="visible"
            initial={reduce ? false : "hidden"}
            variants={containerVariants}
          >
            {/* Announcement pill */}
            <motion.div variants={itemVariants}>
              <Link
                className="group mx-auto flex w-fit items-center gap-4 rounded-full border bg-muted p-1 pl-4 shadow-sm transition-colors duration-300 hover:bg-background"
                href="/dashboard"
              >
                <span className="text-foreground text-sm">
                  AI-powered obstacle detection is live
                </span>
                <span className="block h-4 w-0.5 border-l bg-border" />
                <div className="size-6 overflow-hidden rounded-full bg-background duration-500 group-hover:bg-muted">
                  <div className="flex w-12 -translate-x-1/2 duration-500 ease-in-out group-hover:translate-x-0">
                    <span className="flex size-6">
                      <ArrowRight className="m-auto size-3" />
                    </span>
                    <span className="flex size-6">
                      <ArrowRight className="m-auto size-3" />
                    </span>
                  </div>
                </div>
              </Link>
            </motion.div>

            {/* Headline */}
            <motion.h1
              className="mx-auto mt-8 max-w-4xl text-balance font-semibold text-5xl max-md:font-semibold md:text-7xl lg:mt-16 xl:text-[5.25rem]"
              variants={itemVariants}
            >
              SMART EYES FOR EVERY JOURNEY
            </motion.h1>

            {/* Subtext */}
            <motion.p
              className="mx-auto mt-8 max-w-2xl text-balance text-lg text-muted-foreground"
              variants={itemVariants}
            >
              A multimodal AI companion that turns a chest-mounted phone into
              real-time obstacle detection and navigation for visually impaired
              users.
            </motion.p>

            {/* CTAs */}
            <motion.div
              className="mt-12 flex flex-col items-center justify-center gap-2 md:flex-row"
              variants={itemVariants}
            >
              <div className="rounded-[calc(var(--radius-xl)+0.125rem)] border bg-foreground/10 p-0.5">
                <Button asChild className="rounded-xl px-5 text-base" size="lg">
                  <Link href="/register">
                    <span className="text-nowrap">Get Started</span>
                  </Link>
                </Button>
              </div>
              <Button
                asChild
                className="h-10.5 rounded-xl px-5"
                size="lg"
                variant="ghost"
              >
                <Link href="/dashboard">
                  <span className="text-nowrap">Try the Agent</span>
                </Link>
              </Button>
            </motion.div>
          </motion.div>
        </div>

        {/* Mockup preview — placeholder for app screenshot */}
        <motion.div
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          className="relative mt-8 overflow-hidden px-2 sm:mt-12 md:mt-20"
          initial={reduce ? false : { opacity: 0, y: 40, filter: "blur(12px)" }}
          transition={{ type: "spring", bounce: 0.3, duration: 2, delay: 0.75 }}
        >
          <div className="relative mx-auto max-w-6xl overflow-hidden rounded-2xl border bg-background p-4 shadow-lg ring-1 ring-background">
            <div className="relative flex aspect-15/8 items-center justify-center rounded-2xl border border-border/25 bg-gradient-to-b from-muted/50 to-background">
              {/* Mockup placeholder — TODO: replace with real app screenshot */}
              <div className="flex flex-col items-center gap-4 py-20">
                <div className="flex size-16 items-center justify-center rounded-2xl border bg-muted">
                  <ChevronRight className="size-8 text-muted-foreground" />
                </div>
                <p className="text-muted-foreground text-sm">
                  App preview will appear here
                </p>
              </div>
            </div>
          </div>
        </motion.div>
      </div>

      {/* Logo cloud / trust strip */}
      <div className="relative z-10 bg-background pt-16 pb-16 md:pb-32">
        <div className="mx-auto max-w-5xl px-6">
          <p className="mb-8 text-center font-medium text-muted-foreground text-sm">
            Built with industry-leading technology
          </p>
          <div className="mx-auto grid max-w-2xl grid-cols-2 gap-x-8 gap-y-6 md:grid-cols-4">
            {[
              { icon: siLivekit, name: "LiveKit" },
              { icon: siGooglegemini, name: "Gemini AI" },
              { icon: siConvex, name: "Convex" },
              { icon: siNextdotjs, name: "Next.js" },
            ].map(({ icon, name }) => (
              <div className="flex items-center gap-2" key={name}>
                <svg
                  aria-hidden
                  className="size-5 text-muted-foreground/60"
                  fill="currentColor"
                  role="presentation"
                  viewBox="0 0 24 24"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path d={icon.path} />
                </svg>
                <span className="font-semibold text-lg text-muted-foreground tracking-tight">
                  {name}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
