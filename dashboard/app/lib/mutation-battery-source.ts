// Server-only. Reads badges/mutation-battery-summary.json at build time; the
// Worker has no filesystem, so the committed summary is compiled into the
// server bundle. The client takes its types from ./mutation-battery only.
import { parseMutationSummary } from "./mutation-battery";
import type { MutationSummary } from "./mutation-battery";

declare global {
  interface ImportMeta {
    glob<T>(
      pattern: string,
      options: { eager: true; query: string; import: string },
    ): Record<string, T>;
  }
}

// The safety workflow's publish-mutation-badge job commits this file beside the
// badge, so the page and the badge come from the same CI run.
const summarySources = import.meta.glob<string>(
  "../../../badges/mutation-battery-summary.json",
  { eager: true, query: "?raw", import: "default" },
);

let summary: MutationSummary | null = null;

// Throws, and so fails the build, when the file is missing or disagrees with
// itself. Falling back to a number typed here is exactly the drift this file
// exists to prevent.
export function getMutationSummary(): MutationSummary {
  if (summary) return summary;
  const sources = Object.values(summarySources);
  if (sources.length !== 1) {
    throw new Error(
      "badges/mutation-battery-summary.json was not found when this site was built. " +
        "Build from a full checkout of the repository.",
    );
  }
  summary = parseMutationSummary(sources[0]);
  return summary;
}
