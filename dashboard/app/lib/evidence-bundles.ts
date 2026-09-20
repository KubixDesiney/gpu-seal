// Server-only. Reads examples/evidence/ at build time; the Worker has no
// filesystem, so the committed bundles are compiled into the server bundle.
// Never import this from a client component: the bundles are ~170 KB each and
// must not ship to the browser. The client takes types from ./evidence only.
import { summarizeGalleryEntry } from "./evidence";
import type { EvidenceGalleryEntry } from "./evidence";

declare global {
  interface ImportMeta {
    glob<T>(
      pattern: string,
      options: { eager: true; query: string; import: string },
    ): Record<string, T>;
  }
}

// The one place the site is coupled to the directory layout that
// tests/unit/test_committed_evidence.py guards: one run per directory, a
// *.result.json beside its *.environment.json.
const resultSources = import.meta.glob<string>(
  "../../../examples/evidence/*/*.result.json",
  { eager: true, query: "?raw", import: "default" },
);
const environmentSources = import.meta.glob<string>(
  "../../../examples/evidence/*/*.environment.json",
  { eager: true, query: "?raw", import: "default" },
);

type CommittedRun = {
  id: string;
  bundleFile: string;
  resultText: string;
  environmentText: string | null;
};

function splitKey(key: string): { directory: string; file: string } {
  const parts = key.split("/");
  return { directory: parts[parts.length - 2], file: parts[parts.length - 1] };
}

function loadRuns(): Map<string, CommittedRun> {
  const environmentByDirectory = new Map<string, string>();
  for (const [key, text] of Object.entries(environmentSources)) {
    environmentByDirectory.set(splitKey(key).directory, text);
  }

  const runs = new Map<string, CommittedRun>();
  for (const [key, resultText] of Object.entries(resultSources)) {
    const { directory, file } = splitKey(key);
    // The gallery id is the directory, so a second bundle in one directory
    // would silently replace the first. Refuse instead.
    if (runs.has(directory)) {
      throw new Error(`examples/evidence/${directory} holds more than one result bundle.`);
    }
    runs.set(directory, {
      id: directory,
      bundleFile: file,
      resultText,
      environmentText: environmentByDirectory.get(directory) ?? null,
    });
  }
  return runs;
}

// A Map, not an object: request ids are attacker-chosen, and an object lookup
// of "constructor" or "__proto__" would return something that is not a run.
const runs = loadRuns();

let gallery: EvidenceGalleryEntry[] | null = null;

// Newest run first. Run dates are fixed-format UTC, so string order is time
// order.
export function listEvidenceGallery(): EvidenceGalleryEntry[] {
  gallery ??= [...runs.values()]
    .map((run) =>
      summarizeGalleryEntry(run.id, run.bundleFile, run.resultText, run.environmentText),
    )
    .sort((a, b) => b.runDate.localeCompare(a.runDate) || a.id.localeCompare(b.id));
  return gallery;
}

// The committed file exactly as it sits in the repository, so what a visitor
// inspects is the file a reviewer would verify with the CLI.
export function readCommittedBundle(id: string): string | null {
  return runs.get(id)?.resultText ?? null;
}
