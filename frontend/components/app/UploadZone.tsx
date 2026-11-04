"use client";

import { UploadCloud } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import ClickSpark from "@/components/reactbits/ClickSpark";
import SpotlightCard from "@/components/reactbits/SpotlightCard";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

interface UploadZoneProps {
  onFiles: (files: FileList | File[]) => void;
  maxUploadMb: number;
  compact: boolean;
}

export function UploadZone({ onFiles, maxUploadMb, compact }: UploadZoneProps) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const depth = useRef(0);
  const { resolvedTheme } = useTheme();

  const openPicker = useCallback(() => input.current?.click(), []);

  const onDrop = (event: React.DragEvent) => {
    event.preventDefault();
    depth.current = 0;
    setDragging(false);
    if (event.dataTransfer.files.length) onFiles(event.dataTransfer.files);
  };

  return (
    <SpotlightCard
      theme={resolvedTheme}
      spotlightColor="rgba(99, 102, 241, 0.25)"
      className={cn(
        "rounded-2xl border-2 border-dashed transition-colors",
        dragging ? "border-primary bg-primary/5" : "border-border",
      )}
      onDragEnter={(event) => {
        event.preventDefault();
        depth.current += 1;
        setDragging(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={() => {
        depth.current -= 1;
        if (depth.current <= 0) setDragging(false);
      }}
      onDrop={onDrop}
    >
      <div
        role="button"
        tabIndex={0}
        aria-label={`Choose files to convert, or drop them here. Up to ${maxUploadMb} MB each.`}
        onClick={openPicker}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            openPicker();
          }
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-4 rounded-2xl px-6 text-center",
          compact ? "py-8" : "py-14 sm:py-20",
        )}
      >
        <UploadCloud aria-hidden="true" className={cn("text-primary", compact ? "size-8" : "size-12")} />
        <div>
          <p className="text-lg font-semibold">{dragging ? "Release to upload" : "Drop files here"}</p>
          <p className="mt-1 text-sm text-muted-foreground">Up to {maxUploadMb} MB per file · any number of files</p>
        </div>
        <span className="inline-block">
          <ClickSpark sparkColor={["#6366f1", "#22d3ee", "#a855f7"]} sparkCount={10} sparkRadius={26}>
            <span className="inline-flex h-11 items-center rounded-full bg-primary px-6 text-sm font-semibold text-primary-foreground shadow-sm">
              Choose files
            </span>
          </ClickSpark>
        </span>
      </div>
      <input
        ref={input}
        type="file"
        multiple
        hidden
        onChange={(event) => {
          if (event.target.files?.length) onFiles(event.target.files);
          event.target.value = "";
        }}
      />
    </SpotlightCard>
  );
}
