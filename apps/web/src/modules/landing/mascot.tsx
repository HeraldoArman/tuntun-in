import { cn } from "@tuntun-in/ui/lib/utils";
import Image from "next/image";
import type { ComponentProps } from "react";

/**
 * Available robot mascot assets in /public/mascot.
 * Random subset is referenced across landing sections for decoration.
 */
export const MASCOT_NAMES = [
  "robot_01",
  "robot_02",
  "robot_03",
  "robot_04",
  "robot_05",
  "robot_06",
  "robot_07",
  "robot_08",
  "robot_09",
  "robot_10",
  "robot_11",
  "robot_12",
  "robot_13",
  "robot_14",
  "robot_15",
  "robot_16",
] as const;

export type MascotName = (typeof MASCOT_NAMES)[number];

interface MascotProps
  extends Omit<ComponentProps<typeof Image>, "src" | "alt"> {
  /** Tailwind classes controlling absolute placement, size, rotation, opacity. */
  className?: string;
  /** Which robot mascot to render (e.g. "robot_07"). */
  name: MascotName;
}

/**
 * Decorative mascot. Purely ornamental branding — renders an absolutely
 * positioned image with no alt text and pointer-events disabled so it never
 * intercepts clicks or shows up to assistive tech.
 */
export function Mascot({ name, className, ...props }: MascotProps) {
  return (
    <Image
      alt=""
      aria-hidden
      className={cn("pointer-events-none select-none", className)}
      draggable={false}
      height={256}
      priority={false}
      role="presentation"
      src={`/mascot/${name}.webp`}
      width={256}
      {...props}
    />
  );
}
