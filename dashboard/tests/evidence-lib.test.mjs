import assert from "node:assert/strict";
import test from "node:test";

// Loaded as TypeScript through Node's type stripping; see the `test` script.
import {
  ORIGIN_BADGE,
  formatCudaVersion,
  formatRunDate,
  inspectBundleEnvelope,
  parseBundleText,
  summarizeGalleryEntry,
} from "../app/lib/evidence.ts";

function bundle({ envelope, probes = [], extra = {} }) {
  return {
    schema_version: "gpu-seal-result-v1",
    run_id: "run_fixture",
    timestamp_utc: "2026-01-02T03:04:05Z",
    environment: envelope,
    probes: probes.map((flag) => ({ driver_metadata: { backend_is_real: flag } })),
    report_card: {},
    safety: { automatic_publication_allowed: false },
    ...extra,
  };
}

test("a bundle is real only when the envelope says so and no probe says otherwise", () => {
  const real = inspectBundleEnvelope(
    bundle({ envelope: { backend_is_real: "true" }, probes: ["true", "true", "true"] }),
    "real.json",
    10,
  );
  assert.equal(real.origin, "declared-real");
  assert.equal(real.realProbes, 3);
  assert.equal(real.simulatedProbes, 0);
});

test("a simulated envelope is simulated whatever its probes claim", () => {
  const simulated = inspectBundleEnvelope(
    bundle({ envelope: { backend_is_real: "false" }, probes: ["true", "true"] }),
    "sim.json",
    10,
  );
  assert.equal(simulated.origin, "simulated");
});

test("one simulated probe record makes a real-looking bundle simulated", () => {
  const mixed = inspectBundleEnvelope(
    bundle({ envelope: { backend_is_real: "true" }, probes: ["true", "false", "true"] }),
    "mixed.json",
    10,
  );
  assert.equal(mixed.origin, "simulated");
  assert.equal(mixed.simulatedProbes, 1);
  assert.equal(mixed.realProbes, 2);
});

test("a simulated flag on operational_metadata counts as simulated too", () => {
  const inspection = inspectBundleEnvelope(
    {
      environment: { backend_is_real: "true" },
      probes: [{ operational_metadata: { backend_is_real: "false" } }],
    },
    "ops.json",
    10,
  );
  assert.equal(inspection.origin, "simulated");
});

test("no declaration reads as undeclared, never as real", () => {
  const none = inspectBundleEnvelope(bundle({ envelope: {} }), "none.json", 10);
  assert.equal(none.origin, "undeclared");
  assert.equal(none.backendIsReal, "Not declared");
  const noEnvironment = inspectBundleEnvelope({ probes: [] }, "bare.json", 10);
  assert.equal(noEnvironment.origin, "undeclared");
  // Only the string "true" counts; a boolean is not what the runner writes.
  const boolean = inspectBundleEnvelope(bundle({ envelope: { backend_is_real: true } }), "b.json", 10);
  assert.equal(boolean.origin, "undeclared");
});

test("every origin has a badge, so no gallery card can render without a marker", () => {
  assert.deepEqual(Object.keys(ORIGIN_BADGE).sort(), ["declared-real", "simulated", "undeclared"]);
  assert.match(ORIGIN_BADGE["declared-real"], /self-declared/);
  assert.match(ORIGIN_BADGE.simulated, /Simulated/);
});

test("CUDA versions decode the API integer and pass anything else through", () => {
  assert.equal(formatCudaVersion("12090"), "12.9");
  assert.equal(formatCudaVersion("13000"), "13.0");
  assert.equal(formatCudaVersion("11080"), "11.8");
  assert.equal(formatCudaVersion("13.0"), "13.0");
  assert.equal(formatCudaVersion("unknown"), "unknown");
  assert.equal(formatCudaVersion(null), "Not declared");
});

test("run dates are fixed-format UTC and unknown formats are shown as written", () => {
  assert.equal(formatRunDate("2026-09-16T14:02:03Z"), "2026-09-16 14:02 UTC");
  assert.equal(formatRunDate("2026-09-16T14:02:03.5Z"), "2026-09-16 14:02 UTC");
  assert.equal(formatRunDate("2026-09-16T14:02:03+02:00"), "2026-09-16T14:02:03+02:00");
  assert.equal(formatRunDate(null), "Not declared");
});

test("a gallery entry takes origin from the bundle and host facts from the manifest", () => {
  const entry = summarizeGalleryEntry(
    "kaggle-run",
    "run.result.json",
    JSON.stringify(
      bundle({
        envelope: {
          backend_is_real: "true",
          device_name: "Tesla T4",
          cuda_runtime_version: "12090",
          cuda_driver_version: "13000",
        },
        probes: ["true", "true"],
      }),
    ),
    JSON.stringify({ host_kind: "kaggle", gpu_driver_version: "580.1", gpu_model: "ignored" }),
  );
  assert.equal(entry.origin, "declared-real");
  assert.equal(entry.hostKind, "kaggle");
  assert.equal(entry.driverVersion, "580.1");
  assert.equal(entry.gpuModel, "Tesla T4", "the bundle's device name wins over the manifest");
  assert.equal(entry.cudaRuntime, "12.9");
  assert.equal(entry.cudaDriverApi, "13.0");
  assert.equal(entry.runDate, "2026-01-02 03:04 UTC");
  assert.equal(entry.probeCount, 2);
  assert.equal(entry.bundleUrl, "/evidence-gallery/bundles/kaggle-run");
});

test("a simulated bundle in the gallery is marked simulated, not real", () => {
  const entry = summarizeGalleryEntry(
    "sim-run",
    "sim.result.json",
    JSON.stringify(
      bundle({ envelope: { backend: "simulated", backend_is_real: "false" }, probes: ["false"] }),
    ),
    null,
  );
  assert.equal(entry.origin, "simulated");
  assert.equal(entry.backendIsReal, "false");
  assert.equal(entry.realProbes, 0);
});

test("missing host facts are reported as not recorded, never inferred", () => {
  const entry = summarizeGalleryEntry(
    "no-manifest",
    "x.result.json",
    JSON.stringify(bundle({ envelope: { backend_is_real: "true" } })),
    null,
  );
  assert.equal(entry.hostKind, "Not recorded");
  assert.equal(entry.driverVersion, "Not recorded");
  assert.equal(entry.gpuModel, "Not declared");
});

test("ids are encoded into the bundle URL", () => {
  const entry = summarizeGalleryEntry("a b/../c", "x.json", JSON.stringify(bundle({ envelope: {} })), null);
  assert.equal(entry.bundleUrl, "/evidence-gallery/bundles/a%20b%2F..%2Fc");
});

test("unreadable input fails loudly instead of yielding an empty card", () => {
  assert.throws(() => parseBundleText("not json"), SyntaxError);
  assert.throws(() => parseBundleText("[]"), /top-level JSON value must be an object/);
  assert.throws(() => parseBundleText("null"), /top-level JSON value must be an object/);
  assert.throws(() => summarizeGalleryEntry("x", "x.json", "{", null), SyntaxError);
  assert.throws(() => summarizeGalleryEntry("x", "x.json", "{}", "[]"), /object/);
});
