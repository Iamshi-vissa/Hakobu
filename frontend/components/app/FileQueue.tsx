"use client";

import { useWindowVirtualizer } from "@tanstack/react-virtual";
import dynamic from "next/dynamic";
import { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";

import { FileCard } from "@/components/app/FileCard";
import type { AnimatedListItem } from "@/components/reactbits/AnimatedList";
import { usePrefersReducedMotion } from "@/lib/hooks";
import { useTheme } from "@/lib/theme";
import type { ConverterActions, QueueItem } from "@/lib/useConverter";

/** Above this many files the list is virtualised instead of animated. */
export const VIRTUALIZE_AFTER = 50;
const ESTIMATED_ROW = 96;
const GAP = 8;

const AnimatedList = dynamic(() => import("@/components/reactbits/AnimatedList"), {
  ssr: false,
  loading: () => null,
});

interface FileQueueProps {
  items: QueueItem[];
  actions: ConverterActions;
}

function PlainList({ items, actions }: FileQueueProps) {
  return (
    <ul className="flex flex-col gap-2">
      {items.map((item) => (
        <li key={item.id}>
          <FileCard item={item} actions={actions} />
        </li>
      ))}
    </ul>
  );
}

function VirtualList({ items, actions }: FileQueueProps) {
  const listRef = useRef<HTMLDivElement>(null);
  const [offset, setOffset] = useState(0);
  useLayoutEffect(() => setOffset(listRef.current?.offsetTop ?? 0), []);
  const virtualizer = useWindowVirtualizer({
    count: items.length,
    estimateSize: () => ESTIMATED_ROW,
    gap: GAP,
    overscan: 6,
    scrollMargin: offset,
    getItemKey: (index) => items[index].id,
  });
  return (
    <div ref={listRef} role="list" aria-label="Files" className="relative w-full" style={{ height: virtualizer.getTotalSize() }}>
      {virtualizer.getVirtualItems().map((row) => (
        <div
          key={row.key}
          role="listitem"
          ref={virtualizer.measureElement}
          data-index={row.index}
          className="absolute top-0 left-0 w-full"
          style={{ transform: `translateY(${row.start - virtualizer.options.scrollMargin}px)` }}
        >
          <FileCard item={items[row.index]} actions={actions} />
        </div>
      ))}
    </div>
  );
}

export function FileQueue({ items, actions }: FileQueueProps) {
  const reducedMotion = usePrefersReducedMotion();
  const { resolvedTheme } = useTheme();
  const byId = useMemo(() => new Map(items.map((item) => [item.id, item])), [items]);
  const entries = useMemo(() => items.map((item) => ({ id: item.id, title: item.name })), [items]);
  const renderItem = useCallback(
    (entry: AnimatedListItem) => {
      const item = typeof entry === "object" && entry.id !== undefined ? byId.get(String(entry.id)) : undefined;
      return item ? <FileCard item={item} actions={actions} /> : null;
    },
    [byId, actions],
  );

  if (items.length === 0) return null;
  if (items.length > VIRTUALIZE_AFTER) return <VirtualList items={items} actions={actions} />;
  if (reducedMotion) return <PlainList items={items} actions={actions} />;
  return (
    <AnimatedList
      items={entries}
      renderItem={renderItem}
      interactiveItems
      enableArrowNavigation={false}
      selectOnHover={false}
      showGradients={false}
      displayScrollbar={false}
      animation="slide"
      animateOnce
      frame={false}
      theme={resolvedTheme}
      width="100%"
      maxHeight="none"
      gap={GAP}
      className="w-full"
      itemClassName="!cursor-auto !select-text !p-0 ![background:transparent] ![box-shadow:none]"
    />
  );
}
