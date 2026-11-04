import type { Category } from "@/lib/types";

const UNITS = ["B", "KB", "MB", "GB"] as const;

export function formatBytes(bytes: number): string {
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 || value >= 100 ? 0 : 1)} ${UNITS[unit]}`;
}

export const CATEGORY_LABELS: Record<Category, string> = {
  image: "Images",
  document: "Documents",
  spreadsheet: "Spreadsheets & data",
  presentation: "Presentations",
  audio: "Audio",
  video: "Video",
  ebook: "E-books",
  archive: "Archives",
};

export const CATEGORY_ORDER = Object.keys(CATEGORY_LABELS) as Category[];
