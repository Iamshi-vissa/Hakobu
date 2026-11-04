import Link from "next/link";

import { ThemeToggle } from "@/components/app/ThemeToggle";

export function SiteHeader() {
  return (
    <header className="relative z-20 mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
      <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
        <span aria-hidden="true" className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">
          運
        </span>
        Hakobu
      </Link>
      <ThemeToggle />
    </header>
  );
}
