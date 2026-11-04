"use client";

import dynamic from "next/dynamic";

import { useIdle, useIsDesktop, usePrefersReducedMotion } from "@/lib/hooks";
import { useTheme } from "@/lib/theme";

// WebGL background: lazy chunk, client only. Aurora pauses itself while off-screen.
const Aurora = dynamic(() => import("@/components/reactbits/Aurora"), { ssr: false });

// Forest greens with a warm beige band.
const STOPS = ["#1f4d2e", "#6f9e5a", "#d8c9a0"];

export function HeroBackground() {
  const reducedMotion = usePrefersReducedMotion();
  // Phones/tablets keep the static gradient: a live WebGL canvas costs battery and main-thread time there.
  const desktop = useIsDesktop();
  const idle = useIdle();
  const { resolvedTheme } = useTheme();
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
      {/* Static gradient: what mobile and reduced-motion users see, and the backdrop while the canvas loads. */}
      <div className="absolute inset-0 bg-[radial-gradient(60%_60%_at_50%_0%,color-mix(in_oklch,var(--primary)_22%,transparent),transparent)]" />
      {idle && desktop && !reducedMotion && (
        <Aurora
          colorStops={STOPS}
          amplitude={0.9}
          blend={0.55}
          speed={0.6}
          opacity={resolvedTheme === "dark" ? 0.7 : 0.5}
          lightMode={resolvedTheme === "light"}
          dpr={0.5} // a soft blur: half resolution is indistinguishable and ~4× cheaper
          className="absolute inset-0"
        />
      )}
      <div className="absolute inset-x-0 bottom-0 h-24 bg-gradient-to-b from-transparent to-background" />
    </div>
  );
}
