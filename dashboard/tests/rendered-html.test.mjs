import assert from "node:assert/strict";
import { access, readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const evidenceRoot = fileURLToPath(new URL("../../examples/evidence/", import.meta.url));
const distRoot = fileURLToPath(new URL("../dist/", import.meta.url));

// What the server rendered, not what the RSC payload carries: the payload is
// a <script> that would satisfy any text assertion on its own.
function renderedMarkup(html) {
  return html.replace(/<script[\s\S]*?<\/script>/g, "");
}

function visibleText(markup) {
  return markup
    .replace(/<[^>]+>/g, " ")
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ");
}

async function committedRuns() {
  const directories = (await readdir(evidenceRoot, { withFileTypes: true }))
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name);
  return Promise.all(
    directories.map(async (directory) => {
      const files = await readdir(path.join(evidenceRoot, directory));
      const resultFile = files.find((file) => file.endsWith(".result.json"));
      const environmentFile = files.find((file) => file.endsWith(".environment.json"));
      assert.ok(resultFile && environmentFile, `${directory} is missing a bundle or manifest`);
      const resultPath = path.join(evidenceRoot, directory, resultFile);
      return {
        directory,
        resultFile,
        resultText: await readFile(resultPath, "utf8"),
        result: JSON.parse(await readFile(resultPath, "utf8")),
        manifest: JSON.parse(
          await readFile(path.join(evidenceRoot, directory, environmentFile), "utf8"),
        ),
      };
    }),
  );
}

async function filesUnder(directory) {
  const found = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) found.push(...(await filesUnder(full)));
    else found.push(full);
  }
  return found;
}

async function render(pathname = "/", init = {}) {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", String(process.pid) + "-" + String(Date.now()));
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost" + pathname, {
      headers: {
        accept: "text/html",
        host: "localhost",
        "x-forwarded-proto": "http",
      },
      ...init,
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the public GPU-SEAL portal", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /GPU-SEAL/);
  assert.match(html, /Measure the GPU/);
  assert.match(html, /No cloud-provider measurement study has been run yet\./);
  // The verification boundary has to be in the shipped HTML, not applied later
  // by client JavaScript that a reader may never execute.
  assert.match(
    html,
    /Structural inspection is not cryptographic verification\./,
    "the verification banner must be server-rendered",
  );
  assert.match(
    html,
    /gpu-seal verify \.\/out\/&lt;run-id&gt;\.result\.json --public-key \.\/trusted-ed25519\.pem/,
    "the banner must carry the exact external-key verification command",
  );
  assert.match(html, /Run on your GPU/);
  assert.match(html, /The instrument is local-ready\. The provider study is not\./);
  assert.doesNotMatch(html, /Control Room|Workspace snapshot|Prepare local run/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape/);
});

test("ships product metadata, social assets, and reduced-motion support", async () => {
  const [page, dashboard, layout, css, packageJson] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);

  assert.match(page, /GhostMeterDashboard/);
  assert.match(dashboard, /Choose JSON bundle/);
  // The banner is non-dismissible by construction: it takes no dismiss handler
  // and holds no visibility state. Guard both.
  assert.match(dashboard, /function VerificationBanner/);
  assert.doesNotMatch(
    dashboard,
    /VerificationBanner[\s\S]{0,900}(onDismiss|setDismissed|aria-label="Dismiss"|Close banner)/,
    "the verification banner must not gain a dismiss control",
  );
  // A simulated bundle must be readable as simulated from the UI alone.
  assert.match(dashboard, /environment\.backend_is_real/);
  assert.match(dashboard, /Simulated backend/);
  assert.doesNotMatch(
    dashboard,
    /Structural inspection complete/,
    "the inspector must not report completion as though it verified anything",
  );
  assert.match(dashboard, /The web dashboard cannot access your GPU/);
  assert.match(dashboard, /U means unproven, not failed/);
  assert.match(dashboard, /38 \/ 38/);
  assert.match(layout, /GPU-SEAL — Open GPU Cloud Assurance/);
  assert.match(
    layout,
    /robots:\s*\{\s*index:\s*false/,
    "the pre-alpha portal must not be indexable",
  );
  // A shared card carries no page context, so it must state the boundary.
  assert.match(
    layout,
    /nothing cryptographically verified/,
    "social card text must carry the verification boundary",
  );
  assert.match(layout, /\/og\.png/);
  assert.match(layout, /\/favicon\.png/);
  assert.match(css, /prefers-reduced-motion:\s*reduce/);
  assert.match(css, /--signal:\s*#76d842/);
  assert.match(css, /\.public-shell/);
  assert.doesNotMatch(dashboard, /Windows \/ Python|CUDA unavailable|23 \/ 23|Signed bundles/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton|site-creator-vinext-starter/);

  await access(new URL("../public/og.png", import.meta.url));
  await access(new URL("../public/favicon.png", import.meta.url));

  // The file must exist and the Worker must actually route it.
  const robots = await readFile(new URL("../public/robots.txt", import.meta.url), "utf8");
  assert.match(robots, /User-agent: \*/);
  assert.match(robots, /Disallow: \//);
  const workerSource = await readFile(new URL("../worker/index.ts", import.meta.url), "utf8");
  assert.match(
    workerSource,
    /pathname === "\/robots\.txt"/,
    "the Worker must serve /robots.txt from the asset store",
  );
  await assert.rejects(access(new URL("../app/_sites-preview", import.meta.url)));
});

test("server-renders the evidence gallery from the committed bundles", async () => {
  const runs = await committedRuns();
  assert.ok(runs.length > 0, "examples/evidence/ holds no bundles to render");

  const response = await render("/evidence-gallery");
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const markup = renderedMarkup(await response.text());

  // One card per committed directory: a bundle that is committed but missing
  // from the page, or an empty gallery, fails here.
  const articles = markup.match(/<article\b[\s\S]*?<\/article>/g) ?? [];
  const cards = articles.filter((article) => article.includes("gallery-entry"));
  assert.equal(cards.length, runs.length, "the gallery must list every committed bundle");
  assert.doesNotMatch(visibleText(markup), /No committed bundles were found/);

  for (const run of runs) {
    const card = cards.find((article) => article.includes(run.result.run_id));
    assert.ok(card, `no card for ${run.directory}`);
    const text = visibleText(card);

    assert.ok(text.includes(run.manifest.host_kind), `${run.directory}: host kind`);
    assert.ok(text.includes(run.result.environment.device_name), `${run.directory}: GPU model`);
    assert.ok(text.includes(run.manifest.gpu_driver_version), `${run.directory}: driver version`);
    // CUDA versions are the runner's integer encoding decoded to major.minor.
    const decode = (raw) => `${Math.floor(raw / 1000)}.${Math.floor((raw % 1000) / 10)}`;
    assert.ok(
      text.includes(`runtime ${decode(Number(run.result.environment.cuda_runtime_version))}`),
      `${run.directory}: CUDA runtime`,
    );
    assert.ok(
      text.includes(`driver API ${decode(Number(run.result.environment.cuda_driver_version))}`),
      `${run.directory}: CUDA driver API`,
    );
    const stamp = run.result.timestamp_utc;
    assert.ok(
      text.includes(`${stamp.slice(0, 10)} ${stamp.slice(11, 16)} UTC`),
      `${run.directory}: run date`,
    );
    assert.ok(
      text.includes(`Probe records ${run.result.probes.length}`),
      `${run.directory}: probe count`,
    );

    // The real-vs-simulated marker follows backend_is_real, in the markup.
    const declared = run.result.environment.backend_is_real;
    if (declared === "true") {
      assert.match(card, /data-origin="declared-real"/, `${run.directory}: marker`);
      assert.match(text, /Real GPU · self-declared/);
      assert.match(text, /still not provider evidence/);
      assert.doesNotMatch(text, /Simulated backend/);
    } else {
      assert.match(card, /data-origin="simulated"/, `${run.directory}: marker`);
      assert.doesNotMatch(text, /Real GPU/);
    }
    assert.ok(
      text.includes(`environment.backend_is_real = "${declared}"`),
      `${run.directory}: the marker shows the field it is driven by`,
    );
  }
});

test("the gallery route carries the same non-dismissible verification banner", async () => {
  const markup = renderedMarkup(await (await render("/evidence-gallery")).text());
  assert.match(
    markup,
    /Structural inspection is not cryptographic verification\./,
    "the banner must be server-rendered on the gallery route",
  );
  assert.match(
    markup,
    /gpu-seal verify \.\/out\/&lt;run-id&gt;\.result\.json --public-key \.\/trusted-ed25519\.pem/,
    "the banner must carry the exact external-key verification command",
  );
  assert.ok(
    markup.indexOf("Verification disclaimer") < markup.indexOf("<main"),
    "the banner sits above the page content",
  );
  const banner = /<aside[^>]*verification-banner[\s\S]*?<\/aside>/.exec(markup)?.[0] ?? "";
  assert.equal((banner.match(/<button\b/g) ?? []).length, 1, "the only control is Copy");
  assert.match(banner, /Copy/);
  // The page states its own boundary before any bundle is opened.
  const text = visibleText(markup);
  assert.match(text, /Nothing is uploaded, no Python runs against your GPU, and no instance is provisioned/);
  assert.match(text, /This page never checks a signature/);
});

test("serves each committed bundle byte-for-byte and nothing else", async () => {
  const runs = await committedRuns();
  for (const run of runs) {
    const response = await render(`/evidence-gallery/bundles/${run.directory}`);
    assert.equal(response.status, 200);
    assert.match(response.headers.get("content-type") ?? "", /^application\/json\b/);
    assert.equal(response.headers.get("x-content-type-options"), "nosniff");
    assert.match(response.headers.get("x-robots-tag") ?? "", /noindex/);
    assert.equal(await response.text(), run.resultText, `${run.directory} differs from the committed file`);
  }

  // Ids are looked up in a Map of committed directories, never joined into a
  // path, so none of these can name anything else.
  for (const id of ["nope", "constructor", "__proto__", "toString", "..%2F..%2Fpackage.json"]) {
    const response = await render(`/evidence-gallery/bundles/${id}`);
    assert.equal(response.status, 404, `${id} must not resolve`);
  }

  // Read-only: the route exports GET and nothing that could accept a body.
  for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
    const response = await render(`/evidence-gallery/bundles/${runs[0].directory}`, {
      method,
      body: "{}",
    });
    assert.equal(response.status, 405, `${method} must be refused`);
  }
});

test("committed bundles are compiled into the server, never shipped to the browser", async () => {
  const runs = await committedRuns();
  const [clientFiles, serverFiles] = await Promise.all([
    filesUnder(path.join(distRoot, "client")),
    filesUnder(path.join(distRoot, "server")),
  ]);
  const readSources = (files) =>
    Promise.all(
      files.filter((file) => /\.(?:js|mjs|json|html)$/.test(file)).map((file) => readFile(file, "utf8")),
    );
  const [client, server] = await Promise.all([readSources(clientFiles), readSources(serverFiles)]);

  for (const run of runs) {
    const marker = run.result.experiment_id;
    assert.ok(
      server.some((source) => source.includes(marker)),
      `positive control: ${run.directory} should be embedded in the server build`,
    );
    assert.ok(
      !client.some((source) => source.includes(marker)),
      `${run.directory} leaked into a client asset`,
    );
  }
});

test("the client never gains a way to send a bundle anywhere", async () => {
  const [dashboard, lib, route] = await Promise.all([
    readFile(new URL("../app/dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/lib/evidence.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/evidence-gallery/bundles/[id]/route.ts", import.meta.url), "utf8"),
  ]);
  for (const source of [dashboard, lib]) {
    assert.doesNotMatch(
      source,
      /method:\s*["'`](?:POST|PUT|PATCH|DELETE)|sendBeacon|XMLHttpRequest|FormData|WebSocket|EventSource/i,
      "client code must not upload or stream anything",
    );
  }
  // The only request the gallery makes is a GET of a bundle URL.
  assert.match(dashboard, /fetch\(entry\.bundleUrl, \{ method: "GET", credentials: "omit" \}\)/);
  assert.equal((dashboard.match(/\bfetch\(/g) ?? []).length, 1, "the gallery's is the only fetch");
  assert.match(route, /export async function GET\b/);
  assert.doesNotMatch(route, /export (?:async )?function (?:POST|PUT|PATCH|DELETE)\b/);
  // The build-time reader must stay out of the client module graph; the client
  // takes types only.
  assert.doesNotMatch(dashboard, /evidence-bundles/);
  assert.match(dashboard, /import type \{ BundleInspection, EvidenceGalleryEntry \} from "\.\/lib\/evidence"/);
});

test("the origin copy the inspector shows still says simulated means not evidence", async () => {
  const lib = await readFile(new URL("../app/lib/evidence.ts", import.meta.url), "utf8");
  assert.match(lib, /Simulated backend/);
  assert.match(lib, /must never be cited as a measurement of one/);
  assert.match(lib, /Real GPU · self-declared/);
});
