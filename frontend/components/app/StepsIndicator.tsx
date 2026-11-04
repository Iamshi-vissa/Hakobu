"use client";

import dynamic from "next/dynamic";

import { useTheme } from "@/lib/theme";

export const STEPS = ["Upload", "Choose format", "Convert", "Download"] as const;

function StaticSteps({ current }: { current: number }) {
  return (
    <ol className="flex flex-wrap justify-center gap-x-6 gap-y-2 text-sm">
      {STEPS.map((label, index) => (
        <li key={label} aria-current={index + 1 === current ? "step" : undefined}
          className={index + 1 <= current ? "font-semibold text-foreground" : "text-muted-foreground"}>
          {index + 1}. {label}
        </li>
      ))}
    </ol>
  );
}

const StepsBar = dynamic(() => import("@/components/app/StepsBar"), {
  ssr: false,
  loading: () => <div className="h-14" />,
});

/** Read-only progress through the four stages; the static list doubles as the a11y fallback. */
export function StepsIndicator({ current }: { current: number }) {
  const { resolvedTheme } = useTheme();
  return (
    <nav aria-label="Progress" className="mx-auto w-full max-w-xl">
      <p className="sr-only">Step {current} of {STEPS.length}: {STEPS[current - 1]}</p>
      <div aria-hidden="true" className="hidden sm:block">
        <StepsBar steps={STEPS} current={current} theme={resolvedTheme} />
      </div>
      <div aria-hidden="true" className="sm:hidden">
        <StaticSteps current={current} />
      </div>
    </nav>
  );
}
