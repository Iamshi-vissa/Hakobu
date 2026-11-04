"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import { ApiError, startConversion, startMerge, uploadFile, watchJob } from "@/lib/api";
import { notify } from "@/lib/notify";
import type { ConversionOptions, ErrorCode, FormatInfo, JobResponse, TargetInfo, UploadResponse } from "@/lib/types";

export const MAX_PARALLEL_UPLOADS = 3;
const MERGEABLE = new Set(["pdf", "png", "jpg", "webp", "gif", "bmp", "tiff"]);

export type ItemStatus = "uploading" | "ready" | "converting" | "done" | "error";

export interface ItemError {
  code: ErrorCode;
  message: string;
  /** Which stage to repeat on retry; null when retrying can't help. */
  retry: "upload" | "convert" | null;
}

export interface QueueItem {
  id: string;
  name: string;
  size: number;
  status: ItemStatus;
  uploadProgress: number; // 0..1
  progress: number; // conversion, 0..100
  targets: TargetInfo[];
  options: ConversionOptions;
  format?: FormatInfo;
  fileId?: string;
  target?: string;
  jobId?: string;
  output?: { name: string; size: number; count: number };
  error?: ItemError;
  /** Set for synthetic "merged PDF" items, which have no single source file. */
  mergedFrom?: number;
}

type Action =
  | { type: "add"; items: QueueItem[] }
  | { type: "patch"; id: string; patch: Partial<QueueItem> }
  | { type: "uploaded"; id: string; upload: UploadResponse }
  | { type: "job"; id: string; job: JobResponse }
  | { type: "fail"; id: string; error: ItemError }
  | { type: "setAllTargets"; target: string }
  | { type: "remove"; id: string }
  | { type: "clear" };

function reducer(items: QueueItem[], action: Action): QueueItem[] {
  const update = (id: string, fn: (item: QueueItem) => QueueItem) =>
    items.map((item) => (item.id === id ? fn(item) : item));

  switch (action.type) {
    case "add":
      return [...items, ...action.items];
    case "patch":
      return update(action.id, (item) => ({ ...item, ...action.patch }));
    case "uploaded":
      return update(action.id, (item) => ({
        ...item,
        status: "ready",
        uploadProgress: 1,
        fileId: action.upload.file_id,
        format: action.upload.format,
        targets: action.upload.targets,
        // Preselect the most likely target (the backend orders them).
        target: item.target ?? action.upload.targets[0]?.format,
        error: undefined,
      }));
    case "job": {
      const { job } = action;
      return update(action.id, (current) => {
        const item = { ...current, jobId: job.job_id };
        if (job.status === "done") {
          return {
            ...item,
            status: "done",
            progress: 100,
            output: { name: job.output_name ?? item.name, size: job.output_size ?? 0, count: job.output_count },
          };
        }
        if (job.status === "failed") {
          const code = (job.error_code ?? "failed") as ErrorCode;
          return {
            ...item,
            status: "error",
            error: {
              code,
              message: job.error ?? "Conversion failed.",
              retry: code === "corrupted" ? null : "convert",
            },
          };
        }
        return { ...item, status: "converting", progress: job.progress };
      });
    }
    case "fail":
      return update(action.id, (item) => ({ ...item, status: "error", error: action.error }));
    case "setAllTargets":
      return items.map((item) =>
        item.status === "ready" && item.targets.some((t) => t.format === action.target)
          ? { ...item, target: action.target }
          : item,
      );
    case "remove":
      return items.filter((item) => item.id !== action.id);
    case "clear":
      return [];
  }
}

function errorFrom(error: unknown, retry: ItemError["retry"]): ItemError {
  if (error instanceof ApiError) {
    const permanent = ["unsupported_format", "too_large", "unsupported_conversion", "invalid_request"];
    return { code: error.code, message: error.message, retry: permanent.includes(error.code) ? null : retry };
  }
  return { code: "failed", message: "Something went wrong.", retry };
}

/** A tiny FIFO concurrency limiter. */
function createLimiter(limit: number) {
  let active = 0;
  const waiting: Array<() => void> = [];
  const next = () => {
    if (active >= limit) return;
    const run = waiting.shift();
    if (run) {
      active += 1;
      run();
    }
  };
  return <T>(task: () => Promise<T>): Promise<T> =>
    new Promise<T>((resolve, reject) => {
      waiting.push(() => {
        task()
          .then(resolve, reject)
          .finally(() => {
            active -= 1;
            next();
          });
      });
      next();
    });
}

let localIds = 0;
const nextLocalId = () => `local-${Date.now().toString(36)}-${(localIds += 1)}`;

export interface ConverterStats {
  converted: number;
  inputBytes: number;
  outputBytes: number;
  savedBytes: number;
}

export function useConverter(maxUploadMb: number) {
  const [items, dispatch] = useReducer(reducer, []);
  const files = useRef(new Map<string, File>());
  const watchers = useRef(new Map<string, () => void>());
  const controllers = useRef(new Map<string, AbortController>());
  const limiter = useRef(createLimiter(MAX_PARALLEL_UPLOADS));
  const itemsRef = useRef(items);
  useEffect(() => {
    itemsRef.current = items;
  }, [items]);

  useEffect(() => {
    const active = watchers.current;
    const uploads = controllers.current;
    return () => {
      active.forEach((stop) => stop());
      uploads.forEach((controller) => controller.abort());
    };
  }, []);

  const follow = useCallback((id: string, job: JobResponse) => {
    dispatch({ type: "job", id, job });
    if (job.status === "done" || job.status === "failed") return;
    watchers.current.get(id)?.();
    watchers.current.set(
      id,
      watchJob(job.job_id, (update) => {
        dispatch({ type: "job", id, job: update });
        if (update.status === "done" || update.status === "failed") watchers.current.delete(id);
      }),
    );
  }, []);

  const upload = useCallback((id: string) => {
    const file = files.current.get(id);
    if (!file) return;
    const controller = new AbortController();
    controllers.current.set(id, controller);
    dispatch({ type: "patch", id, patch: { status: "uploading", uploadProgress: 0, error: undefined } });
    let lastReported = 0;
    void limiter.current(() =>
      uploadFile(
        file,
        (fraction) => {
          // Throttle re-renders to whole-percent steps.
          if (fraction - lastReported >= 0.01 || fraction === 1) {
            lastReported = fraction;
            dispatch({ type: "patch", id, patch: { uploadProgress: fraction } });
          }
        },
        controller.signal,
      )
        .then((result) => {
          files.current.delete(id); // the server has it now; free the browser's reference
          dispatch({ type: "uploaded", id, upload: result });
        })
        .catch((error: unknown) => {
          if (error instanceof DOMException && error.name === "AbortError") return;
          dispatch({ type: "fail", id, error: errorFrom(error, "upload") });
        })
        .finally(() => controllers.current.delete(id)),
    );
  }, []);

  const addFiles = useCallback(
    (list: FileList | File[]) => {
      const maxBytes = maxUploadMb * 1024 * 1024;
      const added: QueueItem[] = Array.from(list).map((file) => {
        const id = nextLocalId();
        const base: QueueItem = {
          id, name: file.name, size: file.size, status: "uploading",
          uploadProgress: 0, progress: 0, targets: [], options: {},
        };
        if (file.size > maxBytes) {
          return { ...base, status: "error", error: { code: "too_large", message: `Files can be at most ${maxUploadMb} MB.`, retry: null } };
        }
        if (file.size === 0) {
          return { ...base, status: "error", error: { code: "invalid_request", message: "The file is empty.", retry: null } };
        }
        files.current.set(id, file);
        return base;
      });
      dispatch({ type: "add", items: added });
      added.filter((item) => item.status === "uploading").forEach((item) => upload(item.id));
    },
    [maxUploadMb, upload],
  );

  const convert = useCallback(
    async (id: string) => {
      const item = itemsRef.current.find((i) => i.id === id);
      if (!item?.fileId || !item.target) return;
      dispatch({ type: "patch", id, patch: { status: "converting", progress: 0, error: undefined, output: undefined } });
      try {
        follow(id, await startConversion(item.fileId, item.target, item.options));
      } catch (error) {
        dispatch({ type: "fail", id, error: errorFrom(error, "convert") });
        if (error instanceof ApiError && error.code === "rate_limited") notify("error", error.message);
      }
    },
    [follow],
  );

  const convertAll = useCallback(() => {
    itemsRef.current.filter((i) => i.status === "ready" && i.target).forEach((i) => void convert(i.id));
  }, [convert]);

  const retry = useCallback(
    (id: string) => {
      const item = itemsRef.current.find((i) => i.id === id);
      if (item?.error?.retry === "upload") upload(id);
      else if (item?.error?.retry === "convert") void convert(id);
    },
    [convert, upload],
  );

  const remove = useCallback((id: string) => {
    watchers.current.get(id)?.();
    watchers.current.delete(id);
    controllers.current.get(id)?.abort();
    files.current.delete(id);
    dispatch({ type: "remove", id });
  }, []);

  const clear = useCallback(() => {
    watchers.current.forEach((stop) => stop());
    watchers.current.clear();
    controllers.current.forEach((controller) => controller.abort());
    files.current.clear();
    dispatch({ type: "clear" });
  }, []);

  const setTarget = useCallback(
    (id: string, target: string) => dispatch({ type: "patch", id, patch: { target, status: "ready", output: undefined } }),
    [],
  );

  const setOptions = useCallback(
    (id: string, options: ConversionOptions) => dispatch({ type: "patch", id, patch: { options } }),
    [],
  );

  const setAllTargets = useCallback((target: string) => {
    const ready = itemsRef.current.filter((i) => i.status === "ready");
    const unsupported = ready.filter((i) => !i.targets.some((t) => t.format === target)).length;
    dispatch({ type: "setAllTargets", target });
    if (unsupported > 0) {
      notify("info", `${unsupported} file${unsupported === 1 ? "" : "s"} can't be converted to ${target.toUpperCase()} and kept their format.`);
    }
  }, []);

  const mergeable = useMemo(
    () => items.filter((i) => i.fileId && i.format && MERGEABLE.has(i.format.id) && !i.mergedFrom),
    [items],
  );

  const mergeToPdf = useCallback(async () => {
    const sources = mergeable;
    if (sources.length < 2) return;
    const id = nextLocalId();
    dispatch({
      type: "add",
      items: [{
        id, name: "merged.pdf", size: sources.reduce((sum, s) => sum + s.size, 0), status: "converting",
        uploadProgress: 1, progress: 0, targets: [], options: {}, target: "pdf", mergedFrom: sources.length,
      }],
    });
    try {
      follow(id, await startMerge(sources.map((s) => s.fileId as string)));
    } catch (error) {
      dispatch({ type: "fail", id, error: { ...errorFrom(error, null), retry: null } });
    }
  }, [follow, mergeable]);

  const stats = useMemo<ConverterStats>(() => {
    const done = items.filter((i) => i.status === "done" && i.output);
    const inputBytes = done.reduce((sum, i) => sum + i.size, 0);
    const outputBytes = done.reduce((sum, i) => sum + (i.output?.size ?? 0), 0);
    const savedBytes = done.reduce((sum, i) => sum + Math.max(0, i.size - (i.output?.size ?? 0)), 0);
    return { converted: done.length, inputBytes, outputBytes, savedBytes };
  }, [items]);

  const actions = useMemo(
    () => ({ addFiles, convert, convertAll, retry, remove, clear, setTarget, setOptions, setAllTargets, mergeToPdf }),
    [addFiles, convert, convertAll, retry, remove, clear, setTarget, setOptions, setAllTargets, mergeToPdf],
  );

  return { items, stats, canMerge: mergeable.length >= 2, actions };
}

export type ConverterActions = ReturnType<typeof useConverter>["actions"];
