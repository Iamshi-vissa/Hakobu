import type { Metadata, Viewport } from "next";

import { LazyToaster } from "@/components/app/LazyToaster";
import { THEME_INIT_SCRIPT } from "@/lib/theme";

import "./globals.css";

export const metadata: Metadata = {
  title: "Hakobu — carry your files anywhere",
  description:
    "Convert images, documents, spreadsheets, audio, video, e-books and archives in your browser. Files are deleted after an hour.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4eee1" },
    { media: "(prefers-color-scheme: dark)", color: "#0f1a13" },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Applies the saved theme before first paint (no flash). */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-dvh">
        {children}
        <LazyToaster />
      </body>
    </html>
  );
}
