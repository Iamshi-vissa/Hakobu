"use client";

import dynamic from "next/dynamic";

import { useIdle, usePrefersReducedMotion } from "@/lib/hooks";
import { useTheme } from "@/lib/theme";

// WebGL background: lazy chunk, client only. Aurora pauses itself while off-screen.
const Aurora = dynamic(() => import("@/components/reactbits/Aurora"), { ssr: false });

const STOPS = ["#4f46e5", "#22d3ee", "#a855f7"];

export function HeroBackground() {
  const reducedMotion = usePrefersReducedMotion();
  const idle = useIdle();
  const { resolvedTheme } = useTheme();
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
      {/* Static gradient: the reduced-motion version and the backdrop before the canvas loads. */}
      <div className="absolute inset-0 bg-[radial-gradient(60%_60%_at_50%_0%,color-mix(in_oklch,var(--primary)_22%,transparent),transparent)]" />
      {idle && !reducedMotion && (
        <Aurora
          colorStops={STOPS}
          amplitude={0.9}
          blend={0.55}
          speed={0.6}
          opacity={resolvedTheme === "dark" ? 0.7 : 0.45}
          lightMode={resolvedTheme === "light"}
          dpr={1}
          className="absolute inset-0"
        />
      )}
      <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-b from-transparent to-background" />
    </div>
  );
}
