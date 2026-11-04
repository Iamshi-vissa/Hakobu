"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

function subscribeReducedMotion(onChange: () => void): () => void {
  const media = window.matchMedia(REDUCED_MOTION);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

/** True when the user asked the OS to minimise motion (SSR assumes reduced, the safe default). */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia(REDUCED_MOTION).matches,
    () => true,
  );
}

/** Becomes true once the browser is idle after load — used to defer decorative work. */
export function useIdle(timeout = 1500): boolean {
  const [idle, setIdle] = useState(false);
  useEffect(() => {
    const done = () => setIdle(true);
    if ("requestIdleCallback" in window) {
      const handle = window.requestIdleCallback(done, { timeout });
      return () => window.cancelIdleCallback(handle);
    }
    const handle = setTimeout(done, 300);
    return () => clearTimeout(handle);
  }, [timeout]);
  return idle;
}
