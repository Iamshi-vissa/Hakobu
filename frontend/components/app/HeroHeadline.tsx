"use client";

import dynamic from "next/dynamic";

import { usePrefersReducedMotion } from "@/lib/hooks";
import { useTheme } from "@/lib/theme";

const TITLE = "Hakobu — carry your files";
const ACCENT = "anywhere";
// ShinyText parses its colours, so it needs literals (forest green / beige: AA on each theme).
const ACCENT_COLORS = { light: "#2e5e3e", dark: "#d8c9a0" } as const;
const titleClass = "text-4xl font-bold tracking-tight text-balance sm:text-6xl";

function StaticTitle() {
  return (
    <>
      {TITLE} <span className="text-brand-soft">{ACCENT}</span>
    </>
  );
}

// Animated variants load as separate chunks; the static text renders until they arrive.
const BlurText = dynamic(() => import("@/components/reactbits/BlurText"), {
  ssr: false,
  loading: () => <span>{TITLE}</span>,
});
const ShinyText = dynamic(() => import("@/components/reactbits/ShinyText"), {
  ssr: false,
  loading: () => <span className="text-brand-soft">{ACCENT}</span>,
});

export function HeroHeadline() {
  const reducedMotion = usePrefersReducedMotion();
  const { resolvedTheme } = useTheme();
  return (
    <h1 id="hero-title" className={titleClass} aria-label={`${TITLE} ${ACCENT}`}>
      {reducedMotion ? (
        <StaticTitle />
      ) : (
        <span aria-hidden="true" className="inline-flex flex-wrap items-baseline justify-center gap-x-[0.25em]">
          <BlurText text={TITLE} animateBy="words" delay={90} className="inline-flex flex-wrap justify-center" trigger="load" />
          <ShinyText
            text={ACCENT}
            color={ACCENT_COLORS[resolvedTheme]}
            shineColor={resolvedTheme === "dark" ? "#fbf7ee" : "#8fc79c"}
            speed={3}
            className="inline-block"
          />
        </span>
      )}
    </h1>
  );
}
