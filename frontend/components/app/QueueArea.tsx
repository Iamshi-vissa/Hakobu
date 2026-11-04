"use client";

import { BatchBar } from "@/components/app/BatchBar";
import { FileQueue } from "@/components/app/FileQueue";
import { ResultStats } from "@/components/app/ResultStats";
import type { ConverterActions, ConverterStats, QueueItem } from "@/lib/useConverter";

interface QueueAreaProps {
  items: QueueItem[];
  stats: ConverterStats;
  actions: ConverterActions;
  canMerge: boolean;
}

/** Everything that only matters once files exist; loaded as its own chunk. */
export default function QueueArea({ items, stats, actions, canMerge }: QueueAreaProps) {
  return (
    <>
      <BatchBar items={items} actions={actions} canMerge={canMerge} />
      <FileQueue items={items} actions={actions} />
      <ResultStats stats={stats} />
    </>
  );
}
