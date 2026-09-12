import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", String(process.pid) + "-" + String(Date.now()));
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: {
        accept: "text/html",
        host: "localhost",
        "x-forwarded-proto": "http",
      },
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
  assert.match(layout, /\/og\.png/);
  assert.match(layout, /\/favicon\.png/);
  assert.match(css, /prefers-reduced-motion:\s*reduce/);
  assert.match(css, /--signal:\s*#76d842/);
  assert.match(css, /\.public-shell/);
  assert.doesNotMatch(dashboard, /Windows \/ Python|CUDA unavailable|23 \/ 23|Signed bundles/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton|site-creator-vinext-starter/);

  await access(new URL("../public/og.png", import.meta.url));
  await access(new URL("../public/favicon.png", import.meta.url));
  await assert.rejects(access(new URL("../app/_sites-preview", import.meta.url)));
});
