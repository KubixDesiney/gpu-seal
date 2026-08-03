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

test("server-renders the Ghost Meter control room", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /GPU-SEAL/);
  assert.match(html, /Ghost Meter Control Room/);
  assert.match(html, /Evidence before assurance\./);
  assert.match(html, /No cloud claim exists yet\./);
  assert.match(html, /Prepare local run/);
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
  assert.match(dashboard, /Independent grades, never a composite score/);
  assert.match(dashboard, /Simulation mode locked on/);
  assert.match(layout, /GPU-SEAL — Ghost Meter Control Room/);
  assert.match(layout, /\/og\.png/);
  assert.match(layout, /\/favicon\.png/);
  assert.match(css, /prefers-reduced-motion:\s*reduce/);
  assert.match(css, /--signal:\s*#76d842/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton|site-creator-vinext-starter/);

  await access(new URL("../public/og.png", import.meta.url));
  await access(new URL("../public/favicon.png", import.meta.url));
  await assert.rejects(access(new URL("../app/_sites-preview", import.meta.url)));
});
