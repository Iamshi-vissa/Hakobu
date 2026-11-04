"use client";

import type { CSSProperties } from "react";

import Stepper, { Step } from "@/components/reactbits/Stepper";

// Stepper reads its palette from CSS variables; point them at Hakobu's beige/green tokens.
const STEPPER_COLORS = {
  "--stepper-frame": "var(--muted)",
  "--stepper-frame-edge": "var(--border)",
  "--stepper-tile": "var(--card)",
  "--stepper-tile-edge": "var(--border)",
  "--stepper-ink": "var(--foreground)",
  "--stepper-muted": "var(--muted-foreground)",
  "--stepper-track": "var(--border)",
} as CSSProperties;

interface StepsBarProps {
  steps: readonly string[];
  current: number;
  theme: "light" | "dark";
}

/** Controlled, display-only React Bits Stepper (no footer, no clickable indicators). */
export default function StepsBar({ steps, current, theme }: StepsBarProps) {
  return (
    <Stepper
      step={current}
      showFooter={false}
      disableStepIndicators
      frame={false}
      transition="none"
      indicator="numbers"
      theme={theme}
      accentColor={theme === "dark" ? "#8fc79c" : "#2e5e3e"}
      style={STEPPER_COLORS}
      width="100%"
      contentClassName="hidden"
    >
      {steps.map((label) => (
        <Step key={label} title={label} />
      ))}
    </Stepper>
  );
}
