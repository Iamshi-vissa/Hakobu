/** Toasts without putting Sonner in the initial bundle: the library loads on first use. */
export function notify(kind: "info" | "error" | "success", message: string): void {
  void import("sonner").then(({ toast }) => toast[kind](message));
}
