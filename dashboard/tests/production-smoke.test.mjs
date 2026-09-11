import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import test from "node:test";

const clientRoot = fileURLToPath(new URL("../dist/client/", import.meta.url));
const workerUrl = new URL("../dist/server/index.js", import.meta.url);

function contentType(filePath) {
  if (filePath.endsWith(".css")) return "text/css; charset=utf-8";
  if (filePath.endsWith(".js")) return "text/javascript; charset=utf-8";
  if (filePath.endsWith(".png")) return "image/png";
  return "application/octet-stream";
}

async function assetsFetch(request) {
  const pathname = decodeURIComponent(new URL(request.url).pathname);
  if (
    !pathname.startsWith("/assets/") &&
    !pathname.startsWith("/_next/static/") &&
    pathname !== "/favicon.png" &&
    pathname !== "/og.png"
  ) {
    return new Response("Not found", { status: 404 });
  }
  const relative = pathname.replace(/^\//, "");
  const filePath = path.resolve(clientRoot, relative);
  if (!filePath.startsWith(path.resolve(clientRoot) + path.sep)) {
    return new Response("Not found", { status: 404 });
  }
  try {
    const body = await readFile(filePath);
    return new Response(body, {
      status: 200,
      headers: { "content-type": contentType(filePath) },
    });
  } catch {
    return new Response("Not found", { status: 404 });
  }
}

async function render() {
  const { default: worker } = await import(workerUrl.href + `?test=${Date.now()}`);
  return worker.fetch(
    new Request("http://localhost/"),
    { ASSETS: { fetch: assetsFetch } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("production worker serves every referenced CSS and JavaScript asset", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  const assets = [...html.matchAll(/(?:href|src)="(\/(?:assets|_next\/static)\/[^"?#]+)"/g)]
    .map((match) => match[1])
    .filter((asset) => /\.(?:css|js)$/.test(asset));
  assert.ok(assets.length > 0, "the production HTML must reference CSS and JavaScript");

  for (const asset of new Set(assets)) {
    const assetResponse = await renderAsset(asset);
    assert.equal(assetResponse.status, 200, `${asset} returned ${assetResponse.status}`);
    assert.match(
      assetResponse.headers.get("content-type") ?? "",
      /(?:css|javascript)/,
      `${asset} did not return a CSS/JavaScript content type`,
    );
  }
});

async function renderAsset(asset) {
  const { default: worker } = await import(
    workerUrl.href + `?asset=${encodeURIComponent(asset)}`,
  );
  return worker.fetch(
    new Request(`http://localhost${asset}`),
    { ASSETS: { fetch: assetsFetch } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}
