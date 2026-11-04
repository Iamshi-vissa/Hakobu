"use client";

import Stepper, { Step } from "@/components/reactbits/Stepper";

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
      accentColor="#4f46e5"
      width="100%"
      contentClassName="hidden"
    >
      {steps.map((label) => (
        <Step key={label} title={label} />
      ))}
    </Stepper>
  );
}
