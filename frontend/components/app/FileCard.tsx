"use client";

import {
  AlertCircle,
  Archive,
  BookOpen,
  CheckCircle2,
  Download,
  File,
  FileText,
  Film,
  Image as ImageIcon,
  Loader2,
  Music,
  Presentation,
  RotateCcw,
  Sheet,
  X,
} from "lucide-react";
import { memo } from "react";

import { OptionsDialog, optionGroups } from "@/components/app/OptionsDialog";
import { TargetSelect } from "@/components/app/TargetSelect";
import { Button } from "@/components/ui/button";
import { downloadUrl } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import type { Category } from "@/lib/types";
import type { ConverterActions, QueueItem } from "@/lib/useConverter";
import { cn } from "@/lib/utils";

const ICONS: Record<Category, typeof File> = {
  image: ImageIcon, document: FileText, spreadsheet: Sheet, presentation: Presentation,
  audio: Music, video: Film, ebook: BookOpen, archive: Archive,
};

const ERROR_TITLES: Partial<Record<string, string>> = {
  unsupported_format: "Unsupported format",
  unsupported_conversion: "Can't convert",
  too_large: "Too large",
  corrupted: "File looks corrupted",
  rate_limited: "Slow down",
  network: "Connection problem",
};

function ProgressBar({ value, label }: { value: number; label: string }) {
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(value)}
      className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
    >
      <div className="h-full rounded-full bg-primary transition-[width] duration-300" style={{ width: `${value}%` }} />
    </div>
  );
}

function StatusLine({ item }: { item: QueueItem }) {
  switch (item.status) {
    case "uploading":
      return <ProgressBar value={item.uploadProgress * 100} label={`Uploading ${item.name}`} />;
    case "converting":
      return <ProgressBar value={item.progress} label={`Converting ${item.name}`} />;
    case "done":
      return (
        <p className="flex items-center gap-1.5 text-sm text-success">
          <CheckCircle2 className="size-4" aria-hidden="true" />
          {item.output?.count && item.output.count > 1 ? `${item.output.count} files · ` : ""}
          {formatBytes(item.output?.size ?? 0)}
        </p>
      );
    case "error":
      return (
        <p className="flex items-start gap-1.5 text-sm text-destructive" role="alert">
          <AlertCircle className="mt-0.5 size-4 flex-none" aria-hidden="true" />
          <span>
            <strong className="font-semibold">{ERROR_TITLES[item.error?.code ?? ""] ?? "Failed"}:</strong>{" "}
            {item.error?.message}
          </span>
        </p>
      );
    default:
      return null;
  }
}

interface FileCardProps {
  item: QueueItem;
  actions: ConverterActions;
}

export const FileCard = memo(function FileCard({ item, actions }: FileCardProps) {
  const Icon = item.format ? ICONS[item.format.category] : File;
  const busy = item.status === "uploading" || item.status === "converting";
  const groups = optionGroups(item.format?.category, item.format?.id, item.target);

  return (
    <article
      aria-label={item.name}
      className={cn(
        "flex w-full flex-col gap-3 rounded-xl border bg-card p-3 text-card-foreground shadow-xs sm:flex-row sm:items-center sm:p-4",
        item.status === "error" && "border-destructive/40",
      )}
    >
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <span className="grid size-10 flex-none place-items-center rounded-lg bg-accent text-accent-foreground">
          {busy ? <Loader2 className="size-5 animate-spin" aria-hidden="true" /> : <Icon className="size-5" aria-hidden="true" />}
        </span>
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex items-baseline gap-2">
            <p className="truncate font-medium" title={item.name}>{item.status === "done" ? item.output?.name : item.name}</p>
            {item.format && (
              <span className="flex-none rounded bg-secondary px-1.5 py-0.5 text-[11px] font-semibold tracking-wide text-secondary-foreground uppercase">
                {item.format.extension}
                {item.status === "done" && item.target && item.target !== item.format.id && (
                  <>
                    <span aria-hidden="true"> → </span>
                    <span className="sr-only"> to </span>
                    {item.target}
                  </>
                )}
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            {item.mergedFrom
              ? `${item.status === "done" ? "Merged" : "Merging"} ${item.mergedFrom} files`
              : formatBytes(item.size)}
            {item.format && ` · ${item.format.label}`}
          </p>
          <StatusLine item={item} />
        </div>
      </div>

      <div className="flex flex-none items-center gap-1.5 sm:gap-2">
        {!item.mergedFrom && item.status !== "done" && item.targets.length > 0 && (
          <TargetSelect
            targets={item.targets}
            value={item.target}
            onChange={(format) => actions.setTarget(item.id, format)}
            disabled={busy}
            label={`Target format for ${item.name}`}
          />
        )}
        {!item.mergedFrom && item.status !== "done" && (
          <OptionsDialog
            name={item.name}
            groups={groups}
            options={item.options}
            onSave={(options) => actions.setOptions(item.id, options)}
            disabled={busy}
          />
        )}
        {item.status === "ready" && (
          <Button onClick={() => void actions.convert(item.id)} disabled={!item.target}>Convert</Button>
        )}
        {item.status === "error" && item.error?.retry && (
          <Button variant="outline" onClick={() => actions.retry(item.id)}>
            <RotateCcw className="size-4" aria-hidden="true" /> Retry
          </Button>
        )}
        {item.status === "done" && item.jobId && (
          <>
            <Button asChild>
              <a href={downloadUrl(item.jobId)} download={item.output?.name}>
                <Download className="size-4" aria-hidden="true" /> Download
              </a>
            </Button>
            {!item.mergedFrom && (
              <Button variant="outline" onClick={() => actions.setTarget(item.id, item.target ?? "")}>
                Convert again
              </Button>
            )}
          </>
        )}
        <Button variant="ghost" size="icon" onClick={() => actions.remove(item.id)} aria-label={`Remove ${item.name}`}>
          <X className="size-4" aria-hidden="true" />
        </Button>
      </div>
    </article>
  );
});
