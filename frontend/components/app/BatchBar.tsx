"use client";

import { Download, Layers, Play, Trash2 } from "lucide-react";
import { useMemo } from "react";

import { TargetSelect } from "@/components/app/TargetSelect";
import { Button } from "@/components/ui/button";
import { batchDownloadUrl } from "@/lib/api";
import type { TargetInfo } from "@/lib/types";
import type { ConverterActions, QueueItem } from "@/lib/useConverter";

interface BatchBarProps {
  items: QueueItem[];
  actions: ConverterActions;
  canMerge: boolean;
}

export function BatchBar({ items, actions, canMerge }: BatchBarProps) {
  const ready = items.filter((i) => i.status === "ready");
  const doneJobs = items.filter((i) => i.status === "done" && i.jobId).map((i) => i.jobId as string);

  // Union of targets across ready files, ranked by how many files support each.
  const sharedTargets = useMemo(() => {
    const counts = new Map<string, { target: TargetInfo; count: number; order: number }>();
    for (const item of ready) {
      item.targets.forEach((target, order) => {
        const entry = counts.get(target.format);
        if (entry) entry.count += 1;
        else counts.set(target.format, { target, count: 1, order });
      });
    }
    return [...counts.values()].sort((a, b) => b.count - a.count || a.order - b.order).map((e) => e.target);
  }, [ready]);

  const commonTarget = ready.length > 0 && ready.every((i) => i.target === ready[0].target) ? ready[0].target : undefined;

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-card/60 p-3 backdrop-blur">
      {ready.length > 1 && (
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">All to</span>
          <TargetSelect
            targets={sharedTargets}
            value={commonTarget}
            onChange={actions.setAllTargets}
            label="Set every file to one target format"
            placeholder="Choose…"
          />
        </div>
      )}
      {ready.length > 0 && (
        <Button onClick={actions.convertAll}>
          <Play className="size-4" aria-hidden="true" /> Convert {ready.length > 1 ? `all (${ready.length})` : ""}
        </Button>
      )}
      {canMerge && (
        <Button variant="outline" onClick={() => void actions.mergeToPdf()}>
          <Layers className="size-4" aria-hidden="true" /> Merge into one PDF
        </Button>
      )}
      <div className="ml-auto flex items-center gap-2">
        {doneJobs.length > 1 && (
          <Button asChild variant="secondary">
            <a href={batchDownloadUrl(doneJobs)} download="hakobu-files.zip">
              <Download className="size-4" aria-hidden="true" /> Download all as ZIP
            </a>
          </Button>
        )}
        <Button variant="ghost" onClick={actions.clear}>
          <Trash2 className="size-4" aria-hidden="true" /> Clear
        </Button>
      </div>
    </div>
  );
}
