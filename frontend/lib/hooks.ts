"use client";

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

/** Live result of a CSS media query; ``serverValue`` is used for SSR and hydration. */
export function useMediaQuery(query: string, serverValue: boolean): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const media = window.matchMedia(query);
      media.addEventListener("change", onChange);
      return () => media.removeEventListener("change", onChange);
    },
    [query],
  );
  return useSyncExternalStore(subscribe, () => window.matchMedia(query).matches, () => serverValue);
}

/** True when the user asked the OS to minimise motion (SSR assumes reduced, the safe default). */
export function usePrefersReducedMotion(): boolean {
  return useMediaQuery("(prefers-reduced-motion: reduce)", true);
}

/** Desktop-class device: precise pointer and a wide viewport (SSR assumes not). */
export function useIsDesktop(): boolean {
  return useMediaQuery("(pointer: fine) and (min-width: 768px)", false);
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
