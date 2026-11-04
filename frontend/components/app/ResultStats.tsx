"use client";

import dynamic from "next/dynamic";

import { formatBytes } from "@/lib/format";
import type { ConverterStats } from "@/lib/useConverter";

const CountUp = dynamic(() => import("@/components/reactbits/CountUp"), {
  ssr: false,
  loading: () => <span>0</span>,
});

/** Pick a unit that keeps small results readable (e.g. 840 KB rather than 0.0 MB). */
function scaled(bytes: number): { value: number; suffix: string; decimals: number } {
  if (bytes >= 1024 ** 3) return { value: bytes / 1024 ** 3, suffix: " GB", decimals: 2 };
  if (bytes >= 1024 ** 2) return { value: bytes / 1024 ** 2, suffix: " MB", decimals: 1 };
  return { value: bytes / 1024, suffix: " KB", decimals: 0 };
}

function Stat({ value, decimals = 0, suffix, label }: { value: number; decimals?: number; suffix?: string; label: string }) {
  return (
    <div className="flex flex-col items-center">
      <span className="text-2xl font-bold tabular-nums sm:text-3xl">
        <CountUp to={value} decimals={decimals} suffix={suffix} duration={0.8} trigger="load" />
      </span>
      <span className="text-xs text-muted-foreground sm:text-sm">{label}</span>
    </div>
  );
}

export function ResultStats({ stats }: { stats: ConverterStats }) {
  if (stats.converted === 0) return null;
  const saved = scaled(stats.savedBytes);
  const output = scaled(stats.outputBytes);
  return (
    <section aria-label="Results" className="grid grid-cols-2 gap-4 rounded-xl border bg-card p-4 sm:grid-cols-3">
      <p className="sr-only" aria-live="polite">
        {stats.converted} files converted, {formatBytes(stats.outputBytes)} produced, {formatBytes(stats.savedBytes)} saved.
      </p>
      <Stat value={stats.converted} label={stats.converted === 1 ? "file converted" : "files converted"} />
      <Stat {...output} label="produced" />
      <div className="col-span-2 sm:col-span-1">
        <Stat {...saved} label="saved" />
      </div>
    </section>
  );
}
