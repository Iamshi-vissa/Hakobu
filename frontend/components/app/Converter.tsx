"use client";

import dynamic from "next/dynamic";
import useSWR from "swr";

import { StepsIndicator } from "@/components/app/StepsIndicator";
import { UploadZone } from "@/components/app/UploadZone";
import { fetchFormats } from "@/lib/api";
import { type QueueItem, useConverter } from "@/lib/useConverter";

const DEFAULT_MAX_UPLOAD_MB = 200;

const QueueArea = dynamic(() => import("@/components/app/QueueArea"), { ssr: false });

function currentStep(items: QueueItem[]): number {
  const live = items.filter((i) => i.status !== "error");
  if (live.length === 0) return 1;
  if (live.some((i) => i.status === "converting")) return 3;
  if (live.every((i) => i.status === "done")) return 4;
  return 2;
}

export function Converter() {
  // The matrix never changes while the page is open; fetch once (HTTP caching + ETag do the rest).
  const { data: formats, error } = useSWR("formats", fetchFormats, {
    revalidateOnFocus: false,
    revalidateOnReconnect: false,
    revalidateIfStale: false,
  });
  const maxUploadMb = formats?.max_upload_mb ?? DEFAULT_MAX_UPLOAD_MB;
  const { items, stats, canMerge, actions } = useConverter(maxUploadMb);

  return (
    <section id="converter" aria-label="Converter" className="mx-auto flex max-w-4xl flex-col gap-5 px-4 pb-10">
      <StepsIndicator current={currentStep(items)} />
      {error && (
        <p role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          Hakobu&apos;s server isn&apos;t responding right now. You can still pick files — uploads will retry.
        </p>
      )}
      <UploadZone onFiles={actions.addFiles} maxUploadMb={maxUploadMb} compact={items.length > 0} />
      {items.length > 0 && <QueueArea items={items} stats={stats} actions={actions} canMerge={canMerge} />}
    </section>
  );
}
