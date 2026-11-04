"use client";

import { SlidersHorizontal } from "lucide-react";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { Category, ConversionOptions } from "@/lib/types";

type Group = "resize" | "quality" | "metadata" | "dpi" | "pdf" | "media" | "sampleRate";

const LOSSY = new Set(["jpg", "webp", "avif", "heic"]);
const AUDIO = new Set(["mp3", "wav", "aac", "m4a", "ogg", "flac", "opus"]);

/** Which option groups matter for a source category → target format. */
export function optionGroups(source: Category | undefined, sourceFormat: string | undefined, target: string | undefined): Group[] {
  if (!source || !target) return [];
  const groups: Group[] = [];
  const imageTarget = ["png", "jpg", "webp", "gif", "bmp", "tiff", "heic", "avif", "ico"].includes(target);
  if (sourceFormat === "pdf" && target === "pdf") groups.push("pdf");
  else if (sourceFormat === "pdf" && imageTarget) groups.push("dpi", "resize");
  else if (source === "image" && imageTarget) groups.push("resize", "metadata");
  if (imageTarget && LOSSY.has(target)) groups.push("quality");
  if (source === "audio" || source === "video") {
    groups.push("media");
    if (AUDIO.has(target)) groups.push("sampleRate");
  }
  return groups;
}

interface OptionsDialogProps {
  name: string;
  groups: Group[];
  options: ConversionOptions;
  onSave: (options: ConversionOptions) => void;
  disabled?: boolean;
}

function NumberField({ id, label, value, onChange, min, max, step, suffix }: {
  id: string; label: string; value: number | undefined; onChange: (v: number | undefined) => void;
  min?: number; max?: number; step?: number; suffix?: string;
}) {
  return (
    <label htmlFor={id} className="grid gap-1 text-sm">
      <span className="font-medium">{label}{suffix && <span className="font-normal text-muted-foreground"> ({suffix})</span>}</span>
      <input
        id={id}
        type="number"
        inputMode="decimal"
        min={min}
        max={max}
        step={step}
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value === "" ? undefined : Number(event.target.value))}
        className="h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-xs"
      />
    </label>
  );
}

function CheckField({ id, label, checked, onChange }: { id: string; label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label htmlFor={id} className="flex items-center gap-2 text-sm">
      <input id={id} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="size-4 accent-[var(--primary)]" />
      {label}
    </label>
  );
}

/** Drop empty values so the cache key and payload only carry what the user set. */
function clean(options: ConversionOptions): ConversionOptions {
  return Object.fromEntries(
    Object.entries(options).filter(([, v]) => v !== undefined && v !== "" && v !== false && !Number.isNaN(v)),
  ) as ConversionOptions;
}

export function OptionsDialog({ name, groups, options, onSave, disabled }: OptionsDialogProps) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<ConversionOptions>(options);
  const id = useId();
  const set = <K extends keyof ConversionOptions>(key: K, value: ConversionOptions[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));
  const has = (group: Group) => groups.includes(group);
  const active = Object.keys(clean(options)).length;

  if (groups.length === 0) return null;
  return (
    <Dialog open={open} onOpenChange={(next) => { setOpen(next); if (next) setDraft(options); }}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" disabled={disabled} aria-label={`Advanced options for ${name}${active ? ` (${active} set)` : ""}`}>
          <SlidersHorizontal className="size-4" aria-hidden="true" />
          {active > 0 && <span className="sr-only">{active} options set</span>}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Advanced options</DialogTitle>
          <DialogDescription className="truncate">{name}</DialogDescription>
        </DialogHeader>
        <form
          id={`${id}-form`}
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            onSave(clean(draft));
            setOpen(false);
          }}
        >
          {(has("resize") || has("dpi")) && (
            <div className="grid grid-cols-2 gap-3">
              <NumberField id={`${id}-w`} label="Max width" suffix="px" min={1} max={16384} value={draft.width} onChange={(v) => set("width", v)} />
              {has("resize") && (
                <NumberField id={`${id}-h`} label="Max height" suffix="px" min={1} max={16384} value={draft.height} onChange={(v) => set("height", v)} />
              )}
              {has("dpi") && (
                <NumberField id={`${id}-dpi`} label="Resolution" suffix="DPI" min={36} max={600} value={draft.dpi} onChange={(v) => set("dpi", v)} />
              )}
            </div>
          )}
          {has("quality") && (
            <NumberField id={`${id}-q`} label="Quality" suffix="1–100" min={1} max={100} value={draft.quality} onChange={(v) => set("quality", v)} />
          )}
          {has("metadata") && (
            <CheckField id={`${id}-strip`} label="Strip metadata (EXIF, GPS…)" checked={!!draft.strip_metadata} onChange={(v) => set("strip_metadata", v)} />
          )}
          {has("pdf") && (
            <div className="grid gap-2">
              <CheckField id={`${id}-compress`} label="Compress (smaller file)" checked={!!draft.pdf_compress} onChange={(v) => set("pdf_compress", v)} />
              <CheckField id={`${id}-split`} label="Split into one PDF per page" checked={!!draft.pdf_split} onChange={(v) => set("pdf_split", v)} />
            </div>
          )}
          {has("media") && (
            <div className="grid grid-cols-2 gap-3">
              <NumberField id={`${id}-ts`} label="Trim start" suffix="s" min={0} step={0.1} value={draft.trim_start} onChange={(v) => set("trim_start", v)} />
              <NumberField id={`${id}-te`} label="Trim end" suffix="s" min={0.1} step={0.1} value={draft.trim_end} onChange={(v) => set("trim_end", v)} />
              <label htmlFor={`${id}-br`} className="grid gap-1 text-sm">
                <span className="font-medium">Bitrate <span className="font-normal text-muted-foreground">(e.g. 192k)</span></span>
                <input
                  id={`${id}-br`}
                  pattern="\d{2,5}k"
                  value={draft.bitrate ?? ""}
                  onChange={(e) => set("bitrate", e.target.value || undefined)}
                  className="h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-xs"
                />
              </label>
              {has("sampleRate") && (
                <NumberField id={`${id}-sr`} label="Sample rate" suffix="Hz" min={8000} max={192000} step={100} value={draft.sample_rate} onChange={(v) => set("sample_rate", v)} />
              )}
            </div>
          )}
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => setDraft({})} type="button">Reset</Button>
          <Button type="submit" form={`${id}-form`}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
