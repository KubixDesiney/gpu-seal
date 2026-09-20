// Framework-free reading of a GPU-SEAL result envelope, shared by the
// client-side inspector and the server-rendered evidence gallery. A gallery
// card's real-vs-simulated marker and the label on an inspected upload are
// derived by the same function, so the two cannot disagree about one bundle.
//
// Nothing here does I/O, and nothing here checks a signature, a hash, or a
// key: this is structural reading only. Keep it free of relative imports so
// the unit tests can load it directly under Node's type stripping.

export type BundleOrigin = "simulated" | "declared-real" | "undeclared";

export type BundleInspection = {
  name: string;
  size: string;
  runId: string;
  schema: string;
  probeCount: number;
  reportCard: boolean;
  safetyBlock: boolean;
  backend: string;
  backendIsReal: string;
  simulatedProbes: number;
  realProbes: number;
  publicationAllowed: string;
  origin: BundleOrigin;
  timestamp: string | null;
  deviceName: string | null;
  cudaRuntimeVersion: string | null;
  cudaDriverVersion: string | null;
};

export const ORIGIN_COPY: Record<BundleOrigin, { title: string; detail: string }> = {
  simulated: {
    title: "Simulated backend — not hardware or provider evidence",
    detail:
      "This bundle declares backend_is_real=false. A simulated run exercises the reporting and safety paths only. It says nothing about any GPU and must never be cited as a measurement of one.",
  },
  "declared-real": {
    title: "Declares a real local backend — still not provider evidence",
    detail:
      "backend_is_real=true is the bundle's own claim about itself. This page does not check it and cannot check it. A real local backend is researcher hardware, not a provider measurement.",
  },
  undeclared: {
    title: "Backend origin not declared — treat as unproven",
    detail:
      "This bundle does not declare environment.backend_is_real, so its origin cannot be read structurally at all.",
  },
};

// The short form shown as a card's marker. "self-declared" stays in the real
// label on purpose: it is the bundle's word, not a finding of this site.
export const ORIGIN_BADGE: Record<BundleOrigin, string> = {
  simulated: "Simulated",
  "declared-real": "Real GPU · self-declared",
  undeclared: "Origin not declared",
};

// Reads one string field without trusting the shape of anything around it.
export function readString(source: unknown, key: string): string | null {
  if (!source || typeof source !== "object" || Array.isArray(source)) return null;
  const value = (source as Record<string, unknown>)[key];
  return typeof value === "string" ? value : null;
}

export function readField(source: unknown, key: string): unknown {
  if (!source || typeof source !== "object" || Array.isArray(source)) return null;
  return (source as Record<string, unknown>)[key];
}

export function formatByteSize(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
}

export function parseBundleText(text: string): Record<string, unknown> {
  const parsed: unknown = JSON.parse(text);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("The top-level JSON value must be an object.");
  }
  return parsed as Record<string, unknown>;
}

export function inspectBundleEnvelope(
  bundle: Record<string, unknown>,
  name: string,
  sizeBytes: number,
): BundleInspection {
  const probeList = Array.isArray(bundle.probes) ? bundle.probes : [];
  // The runner stamps origin on the envelope and again on every probe record.
  // A mixed bundle must read as simulated if any record says so.
  const backendIsReal = readString(bundle.environment, "backend_is_real");
  const probeOrigins = probeList.map((probe) => [
    readString(readField(probe, "driver_metadata"), "backend_is_real"),
    readString(readField(probe, "operational_metadata"), "backend_is_real"),
  ]);
  const simulatedProbes = probeOrigins.filter((flags) => flags.includes("false")).length;
  const realProbes = probeOrigins.filter(
    (flags) => flags.includes("true") && !flags.includes("false"),
  ).length;
  const publicationAllowed = readField(bundle.safety, "automatic_publication_allowed");

  return {
    name,
    size: formatByteSize(sizeBytes),
    runId: typeof bundle.run_id === "string" ? bundle.run_id : "Not declared",
    schema: typeof bundle.schema_version === "string" ? bundle.schema_version : "Not declared",
    probeCount: probeList.length,
    reportCard: Boolean(bundle.report_card && typeof bundle.report_card === "object"),
    safetyBlock: Boolean(bundle.safety && typeof bundle.safety === "object"),
    backend: readString(bundle.environment, "backend") ?? "Not declared",
    backendIsReal: backendIsReal ?? "Not declared",
    simulatedProbes,
    realProbes,
    publicationAllowed:
      typeof publicationAllowed === "boolean" ? String(publicationAllowed) : "Not declared",
    origin:
      backendIsReal === "false" || simulatedProbes > 0
        ? "simulated"
        : backendIsReal === "true"
          ? "declared-real"
          : "undeclared",
    timestamp: typeof bundle.timestamp_utc === "string" ? bundle.timestamp_utc : null,
    deviceName: readString(bundle.environment, "device_name"),
    cudaRuntimeVersion: readString(bundle.environment, "cuda_runtime_version"),
    cudaDriverVersion: readString(bundle.environment, "cuda_driver_version"),
  };
}

// The runner records CUDA versions as the integer the API returns
// (1000 * major + 10 * minor), so "12090" is 12.9 and "13000" is 13.0.
// Anything that is not that integer is shown as written, not guessed at.
export function formatCudaVersion(raw: string | null): string {
  if (raw === null) return "Not declared";
  if (!/^\d+$/.test(raw)) return raw;
  const value = Number(raw);
  return `${Math.floor(value / 1000)}.${Math.floor((value % 1000) / 10)}`;
}

// Fixed-format UTC so server and client render the same text; a locale-aware
// formatter would differ between them and between visitors.
export function formatRunDate(timestamp: string | null): string {
  if (timestamp === null) return "Not declared";
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}):\d{2}(?:\.\d+)?Z$/.exec(timestamp);
  return match ? `${match[1]} ${match[2]} UTC` : timestamp;
}

export type EvidenceGalleryEntry = {
  id: string;
  bundleFile: string;
  bundleUrl: string;
  runId: string;
  runDate: string;
  hostKind: string;
  gpuModel: string;
  driverVersion: string;
  cudaRuntime: string;
  cudaDriverApi: string;
  probeCount: number;
  realProbes: number;
  simulatedProbes: number;
  backendIsReal: string;
  origin: BundleOrigin;
};

export const GALLERY_BUNDLE_PATH = "/evidence-gallery/bundles/";

// GPU model, CUDA versions, date, probe count and origin come from the bundle
// itself. Host kind and the NVIDIA driver version exist only in the
// environment.json the operator's host wrote beside it, which is unsigned;
// without that file they read "Not recorded" rather than being inferred.
export function summarizeGalleryEntry(
  id: string,
  bundleFile: string,
  resultText: string,
  environmentText: string | null,
): EvidenceGalleryEntry {
  const inspection = inspectBundleEnvelope(parseBundleText(resultText), bundleFile, 0);
  const manifest = environmentText === null ? null : parseBundleText(environmentText);

  return {
    id,
    bundleFile,
    bundleUrl: GALLERY_BUNDLE_PATH + encodeURIComponent(id),
    runId: inspection.runId,
    runDate: formatRunDate(inspection.timestamp),
    hostKind: readString(manifest, "host_kind") ?? "Not recorded",
    gpuModel: inspection.deviceName ?? readString(manifest, "gpu_model") ?? "Not declared",
    driverVersion: readString(manifest, "gpu_driver_version") ?? "Not recorded",
    cudaRuntime: formatCudaVersion(inspection.cudaRuntimeVersion),
    cudaDriverApi: formatCudaVersion(inspection.cudaDriverVersion),
    probeCount: inspection.probeCount,
    realProbes: inspection.realProbes,
    simulatedProbes: inspection.simulatedProbes,
    backendIsReal: inspection.backendIsReal,
    origin: inspection.origin,
  };
}
