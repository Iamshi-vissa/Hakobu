"use client";

import { memo, useMemo } from "react";

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { CATEGORY_LABELS } from "@/lib/format";
import type { Category, TargetInfo } from "@/lib/types";

interface TargetSelectProps {
  targets: TargetInfo[];
  value: string | undefined;
  onChange: (format: string) => void;
  disabled?: boolean;
  label: string;
  placeholder?: string;
}

/** Target formats grouped by category, keeping the server's "most likely first" order. */
export const TargetSelect = memo(function TargetSelect({
  targets, value, onChange, disabled, label, placeholder = "Convert to…",
}: TargetSelectProps) {
  const groups = useMemo(() => {
    const map = new Map<Category, TargetInfo[]>();
    for (const target of targets) {
      const list = map.get(target.category) ?? [];
      list.push(target);
      map.set(target.category, list);
    }
    return [...map.entries()];
  }, [targets]);

  return (
    <Select value={value} onValueChange={onChange} disabled={disabled || targets.length === 0}>
      <SelectTrigger aria-label={label} className="w-full min-w-36 sm:w-44">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent className="max-h-80">
        {groups.map(([category, list]) => (
          <SelectGroup key={category}>
            <SelectLabel>{CATEGORY_LABELS[category]}</SelectLabel>
            {list.map((target) => (
              <SelectItem key={target.format} value={target.format}>
                {target.label}
                {target.steps > 1 && <span className="ml-1 text-xs text-muted-foreground">· {target.steps} steps</span>}
              </SelectItem>
            ))}
          </SelectGroup>
        ))}
      </SelectContent>
    </Select>
  );
});
