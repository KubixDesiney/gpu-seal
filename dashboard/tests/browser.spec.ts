import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

test("production dashboard loads, hydrates, and inspects an upload locally", async ({ page }) => {
  const assetFailures: string[] = [];
  const consoleErrors: string[] = [];
  page.on("response", (response) => {
    if (
      (response.url().includes("/assets/") || response.url().includes("/_next/static/")) &&
      response.status() >= 400
    ) {
      assetFailures.push(`${response.status()} ${response.url()}`);
    }
  });
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: /Measure the GPU/ })).toBeVisible();
  const banner = page.getByRole("note", { name: "Verification disclaimer" });
  await expect(banner).toBeVisible();
  await expect(banner).toContainText(
    "Structural inspection is not cryptographic verification.",
  );
  await expect(banner).toContainText(
    "gpu-seal verify ./out/<run-id>.result.json --public-key ./trusted-ed25519.pem",
  );
  await expect(page.locator("html")).toHaveAttribute("data-hydrated", "true");
  expect(assetFailures).toEqual([]);
  expect(consoleErrors).toEqual([]);
  await expect(page.locator("link[rel='stylesheet']")).toHaveCount(1);
  await expect(page.locator(".site-header")).toHaveCSS("position", "sticky");

  await page.getByRole("button", { name: "Inspect an example" }).click();
  await expect(page).toHaveURL(/#evidence$/);
  await page.locator("input[type='file']").setInputFiles({
    name: "too-large.result.json",
    mimeType: "application/json",
    buffer: Buffer.alloc(5 * 1024 * 1024 + 1),
  });
  await expect(page.getByText(/no larger than 5 MiB/)).toBeVisible();
  const bundle = {
    schema_version: "gpu-seal-result-v1",
    run_id: "browser-upload",
    probes: [],
    report_card: {},
    safety: { canary_only_search: true },
  };
  await page.locator("input[type='file']").setInputFiles({
    name: "browser-upload.result.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(bundle)),
  });
  await expect(page.getByText(/Structure read/)).toBeVisible();
  await expect(page.getByText(/Trusted verification was not performed/)).toBeVisible();
  // An envelope with no declared backend must say so rather than stay silent.
  await expect(
    page.getByText(/Backend origin not declared/),
  ).toBeVisible();

  // A simulated bundle must be labelled as simulated in the UI, not only in
  // the JSON a reader would have to open by hand.
  const simulated = {
    schema_version: "gpu-seal-result-v1",
    run_id: "simulated-upload",
    environment: { backend: "simulated", backend_is_real: "false" },
    probes: [{ driver_metadata: { backend_is_real: "false" } }],
    report_card: {},
    safety: { canary_only_search: true, automatic_publication_allowed: false },
  };
  await page.locator("input[type='file']").setInputFiles({
    name: "simulated.result.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(simulated)),
  });
  await expect(
    page.getByText(/Simulated backend .* not hardware or provider evidence/),
  ).toBeVisible();
  await expect(page.getByText("environment.backend_is_real")).toBeVisible();
  await expect(page.locator(".upload-simulated")).toBeVisible();

  await page.getByRole("button", { name: /Canonical pinned local battery/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute("aria-modal", "true");
  await expect(
    dialog.getByRole("button", { name: "Close evidence details" }),
  ).toBeFocused();
});

test("the verification banner persists on every page and offers no way out", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  const banner = page.getByRole("note", { name: "Verification disclaimer" });

  for (const label of ["Evidence", "Method", "Providers", "Run it", "Safety"]) {
    await page.getByRole("navigation", { name: "Main navigation" })
      .getByRole("button", { name: label })
      .click();
    await expect(banner).toBeVisible();
  }

  // No control inside the banner may remove it; the only button copies.
  const buttons = banner.getByRole("button");
  await expect(buttons).toHaveCount(1);
  await expect(buttons.first()).toHaveText(/Copy/);
});

test("mobile navigation exposes its open state and the skip link reaches main", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  const skip = page.getByRole("link", { name: "Skip to main content" });
  await skip.focus();
  await skip.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();

  const toggle = page.getByRole("button", { name: "Toggle navigation" });
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("navigation", { name: "Mobile navigation" })).toBeVisible();
});

// ---------------------------------------------------------------------------
// Evidence gallery route
// ---------------------------------------------------------------------------

const VERIFY_COMMAND =
  "gpu-seal verify ./out/<run-id>.result.json --public-key ./trusted-ed25519.pem";
const evidenceRoot = path.resolve(process.cwd(), "../examples/evidence");

// Expected values are read from the committed files here, never restated, so a
// card that drifts from its bundle fails instead of matching a copy of itself.
const committedRuns = readdirSync(evidenceRoot, { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => {
    const files = readdirSync(path.join(evidenceRoot, entry.name));
    const read = (suffix: string) =>
      JSON.parse(
        readFileSync(path.join(evidenceRoot, entry.name, files.find((f) => f.endsWith(suffix))!), "utf8"),
      );
    const result = read(".result.json");
    const manifest = read(".environment.json");
    const decode = (raw: string) => `${Math.floor(Number(raw) / 1000)}.${Math.floor((Number(raw) % 1000) / 10)}`;
    const stamp: string = result.timestamp_utc;
    return {
      directory: entry.name,
      runId: result.run_id as string,
      backendIsReal: result.environment.backend_is_real as string,
      probeCount: result.probes.length as number,
      facts: {
        "Host kind": manifest.host_kind as string,
        "GPU model": result.environment.device_name as string,
        "NVIDIA driver": manifest.gpu_driver_version as string,
        CUDA: `runtime ${decode(result.environment.cuda_runtime_version)} · driver API ${decode(result.environment.cuda_driver_version)}`,
        "Run date": `${stamp.slice(0, 10)} ${stamp.slice(11, 16)} UTC`,
        "Probe records": String(result.probes.length),
      } as Record<string, string>,
    };
  });

test.describe("evidence gallery rendered without JavaScript", () => {
  // Nothing hydrates here, so anything that shows is what the server sent.
  test.use({ javaScriptEnabled: false });

  test("lists every committed bundle with its facts and real-vs-simulated marker", async ({ page }) => {
    expect(committedRuns.length).toBeGreaterThan(0);
    await page.goto("/evidence-gallery", { waitUntil: "domcontentloaded" });
    await expect(page.locator("html")).not.toHaveAttribute("data-hydrated", "true");

    const banner = page.getByRole("note", { name: "Verification disclaimer" });
    await expect(banner).toBeVisible();
    await expect(banner).toContainText("Structural inspection is not cryptographic verification.");
    await expect(banner).toContainText(VERIFY_COMMAND);

    const cards = page.locator("article.gallery-entry");
    await expect(cards).toHaveCount(committedRuns.length);
    for (const run of committedRuns) {
      const card = cards.filter({ hasText: run.runId });
      await expect(card).toHaveCount(1);
      for (const [label, value] of Object.entries(run.facts)) {
        const fact = card.locator(".gallery-facts > div", {
          has: page.locator(`dt:text-is("${label}")`),
        });
        await expect(fact.locator("dd")).toHaveText(value);
      }
      const marker = card.locator(".gallery-origin");
      await expect(marker).toBeVisible();
      await expect(marker).toHaveAttribute(
        "data-origin",
        run.backendIsReal === "true" ? "declared-real" : "simulated",
      );
      await expect(marker).toContainText(
        run.backendIsReal === "true" ? "Real GPU · self-declared" : "Simulated",
      );
      await expect(marker).toContainText(`environment.backend_is_real = "${run.backendIsReal}"`);
      await expect(marker).toContainText("not provider evidence");
    }
  });
});

test("opening committed bundles in the inspector sends nothing anywhere", async ({ page, baseURL }) => {
  const requests: Array<{ method: string; url: string; body: string | null }> = [];
  let sockets = 0;
  const consoleErrors: string[] = [];
  page.on("request", (request) =>
    requests.push({ method: request.method(), url: request.url(), body: request.postData() }),
  );
  page.on("websocket", () => (sockets += 1));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.goto("/evidence-gallery", { waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveAttribute("data-hydrated", "true");

  // The page states its boundary before anything is opened.
  await expect(page.getByRole("region", { name: "What opening a bundle does" })).toContainText(
    "Nothing is uploaded, no Python runs against your GPU, and no instance is provisioned.",
  );

  for (const run of committedRuns) {
    const card = page.locator("article.gallery-entry").filter({ hasText: run.runId });
    const before = requests.length;
    await card.getByRole("button", { name: "Open in inspector" }).click();

    // The same panel the file picker produces, not a lookalike.
    const panel = card.getByRole("status");
    await expect(panel).toBeVisible();
    await expect(panel).toHaveClass(/upload-result/);
    await expect(panel).toHaveClass(run.backendIsReal === "true" ? /upload-declared-real/ : /upload-simulated/);
    await expect(panel).toContainText("Structure read");
    await expect(panel).toContainText("not verified");
    await expect(panel).toContainText("Trusted verification was not performed");
    await expect(panel).toContainText(run.runId);
    await expect(
      panel.locator(".upload-grid > span", { has: page.locator('small:text-is("Probe records")') }),
    ).toContainText(String(run.probeCount));
    if (run.backendIsReal === "true") {
      await expect(panel).toContainText("Declares a real local backend");
      await expect(panel).toContainText("still not provider evidence");
    }

    // Everything that left the browser for that click: one GET, no body, to
    // this origin, for the committed bundle.
    const sent = requests.slice(before);
    expect(sent.length).toBeGreaterThan(0);
    for (const request of sent) {
      expect(request.method).toBe("GET");
      expect(request.body).toBeNull();
      expect(new URL(request.url).origin).toBe(new URL(baseURL!).origin);
    }
    expect(sent.map((request) => new URL(request.url).pathname)).toContain(
      `/evidence-gallery/bundles/${run.directory}`,
    );

    await card.getByRole("button", { name: "Close inspector" }).click();
    await expect(card.locator(".upload-result")).toHaveCount(0);
  }

  // Across the whole visit: nothing was sent, nothing streamed.
  expect(requests.filter((request) => request.method !== "GET")).toEqual([]);
  expect(requests.filter((request) => request.body !== null)).toEqual([]);
  expect(sockets).toBe(0);
  expect(consoleErrors).toEqual([]);

  // No control on this route can run code on a visitor's GPU or start an
  // instance; the only buttons are navigation, copy, and open/close.
  await expect(
    page.getByRole("button", { name: /provision|launch|start (?:an? )?instance|run (?:on|against) (?:my|your|this) gpu|deploy/i }),
  ).toHaveCount(0);
  await expect(page.locator("input[type='file']")).toHaveCount(0);

  const banner = page.getByRole("note", { name: "Verification disclaimer" });
  await expect(banner).toBeVisible();
  await expect(banner).toContainText(VERIFY_COMMAND);
  await expect(banner.getByRole("button")).toHaveCount(1);
  await expect(banner.getByRole("button").first()).toHaveText(/Copy/);
});

test("a gallery bundle is classified by the same code as an upload", async ({ page }) => {
  // The committed bundles are all real, so serve a simulated one in place of
  // the first and require the inspector to say so.
  const simulated = {
    schema_version: "gpu-seal-result-v1",
    run_id: "simulated-from-gallery",
    environment: { backend: "simulated", backend_is_real: "false" },
    probes: [{ driver_metadata: { backend_is_real: "false" } }],
    report_card: {},
    safety: { canary_only_search: true, automatic_publication_allowed: false },
  };
  await page.route("**/evidence-gallery/bundles/*", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(simulated) }),
  );
  await page.goto("/evidence-gallery", { waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveAttribute("data-hydrated", "true");

  const card = page.locator("article.gallery-entry").first();
  await card.getByRole("button", { name: "Open in inspector" }).click();
  await expect(card.getByText(/Simulated backend .* not hardware or provider evidence/)).toBeVisible();
  await expect(card.locator(".upload-simulated")).toBeVisible();
  await expect(card.getByText("environment.backend_is_real", { exact: true })).toBeVisible();
});

test("a bundle that cannot be read shows an error and no inspector panel", async ({ page }) => {
  let respondWith: "missing" | "garbage" = "missing";
  await page.route("**/evidence-gallery/bundles/*", (route) =>
    respondWith === "missing"
      ? route.fulfill({ status: 404, body: "gone" })
      : route.fulfill({ contentType: "application/json", body: "[1, 2" }),
  );
  await page.goto("/evidence-gallery", { waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveAttribute("data-hydrated", "true");

  const card = page.locator("article.gallery-entry").first();
  const open = card.getByRole("button", { name: "Open in inspector" });
  await open.click();
  await expect(card.getByRole("alert")).toContainText("The site answered 404");
  await expect(card.locator(".upload-result")).toHaveCount(0);

  respondWith = "garbage";
  await open.click();
  await expect(card.getByRole("alert")).toBeVisible();
  await expect(card.locator(".upload-result")).toHaveCount(0);
});

test("the verification banner persists on the gallery route and after leaving it", async ({ page }) => {
  await page.goto("/evidence-gallery", { waitUntil: "domcontentloaded" });
  const banner = page.getByRole("note", { name: "Verification disclaimer" });
  await expect(banner).toBeVisible();
  await expect(banner).toContainText(VERIFY_COMMAND);
  await expect(page.locator("html")).toHaveAttribute("data-hydrated", "true");
  // The gallery is a child of Evidence, so that is the nav entry that is lit.
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  await expect(nav.getByRole("button", { name: "Evidence" })).toHaveAttribute("aria-current", "page");

  // No control inside the banner may remove it; the only button copies.
  await expect(banner.getByRole("button")).toHaveCount(1);
  await expect(banner.getByRole("button").first()).toHaveText(/Copy/);

  for (const label of ["Method", "Providers", "Run it", "Safety"]) {
    await page.goto("/evidence-gallery", { waitUntil: "domcontentloaded" });
    await expect(page.locator("html")).toHaveAttribute("data-hydrated", "true");
    await nav.getByRole("button", { name: label }).click();
    await expect(page).toHaveURL(/\/#/);
    await expect(page.locator("html")).toHaveAttribute("data-hydrated", "true");
    await expect(nav.getByRole("button", { name: label })).toHaveAttribute("aria-current", "page");
    await expect(banner).toBeVisible();
    await expect(banner).toContainText(VERIFY_COMMAND);
  }
});

test("the gallery is reachable from the evidence page and links back", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveAttribute("data-hydrated", "true");
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("button", { name: "Evidence" })
    .click();
  await page.getByRole("link", { name: /open a committed hardware bundle/i }).click();
  await expect(page).toHaveURL(/\/evidence-gallery$/);
  await expect(page.locator("article.gallery-entry")).toHaveCount(committedRuns.length);

  await expect(page.locator("html")).toHaveAttribute("data-hydrated", "true");
  await page.getByRole("button", { name: "Back to the evidence explorer" }).click();
  await expect(page).toHaveURL(/\/#evidence$/);
  await expect(page.getByRole("heading", { name: /Inspect the record/ })).toBeVisible();
});

test("the gallery fits a phone-width screen without sideways scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/evidence-gallery", { waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveAttribute("data-hydrated", "true");
  await page.locator("article.gallery-entry").first().getByRole("button", { name: "Open in inspector" }).click();
  await expect(page.locator("article.gallery-entry").first().getByRole("status")).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});

// ---------------------------------------------------------------------------
// Mutation battery route
// ---------------------------------------------------------------------------

type BatteryCase = {
  name: string;
  expected_test: string;
  test_file: string;
  status: string;
  matched_test: string | null;
};

// The expected count is read from the committed CI summary here, never
// restated, so the page cannot drift from it and this test cannot drift with it.
const battery = JSON.parse(
  readFileSync(path.resolve(process.cwd(), "../badges/mutation-battery-summary.json"), "utf8"),
) as { total: number; caught: number; cases: BatteryCase[] };
const batteryFiles = [...new Set(battery.cases.map((c) => c.test_file))];

test.describe("mutation battery rendered without JavaScript", () => {
  // Nothing hydrates here, so anything that shows is what the server sent.
  test.use({ javaScriptEnabled: false });

  test("the case count on the page equals the count in the summary JSON", async ({ page }) => {
    expect(battery.cases.length).toBeGreaterThan(0);
    await page.goto("/mutation-battery", { waitUntil: "domcontentloaded" });
    await expect(page.locator("html")).not.toHaveAttribute("data-hydrated", "true");

    // The headline leads, and it is the JSON's own count.
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      `${battery.caught} of ${battery.total} injected violations caught`,
    );

    // The assertion the page exists to satisfy: rows on the page == cases in the JSON.
    const rows = page.locator("tr.battery-case");
    await expect(rows).toHaveCount(battery.cases.length);
    await expect(rows).toHaveCount(battery.total);
    await expect(page.locator('tr.battery-case[data-status="caught"]')).toHaveCount(battery.caught);

    // The per-file tallies add up to the same total, so grouping dropped nothing.
    const tallies = await page.locator(".battery-tally").allTextContents();
    const shown = tallies.map((text) => /^(\d+) \/ (\d+) caught$/.exec(text.trim()));
    expect(shown.every(Boolean)).toBe(true);
    expect(shown.reduce((sum, m) => sum + Number(m![2]), 0)).toBe(battery.total);
    expect(shown.reduce((sum, m) => sum + Number(m![1]), 0)).toBe(battery.caught);
    await expect(page.locator("details.battery-group")).toHaveCount(batteryFiles.length);
  });

  test("every case is visible on arrival, with what was injected, what caught it, and the verdict", async ({ page }) => {
    await page.goto("/mutation-battery", { waitUntil: "domcontentloaded" });

    // Open on arrival: no group is collapsed and no control has been touched.
    await expect(page.locator("details.battery-group:not([open])")).toHaveCount(0);
    await expect(page.locator("tr.battery-case").first()).toBeVisible();
    await expect(page.locator("tr.battery-case").last()).toBeVisible();

    for (const file of batteryFiles) {
      const group = page.locator("details.battery-group").filter({
        has: page.locator(`.battery-file:text-is("${file}")`),
      });
      await expect(group).toHaveCount(1);
      const expected = battery.cases.filter((c) => c.test_file === file);
      await expect(group.locator("tr.battery-case")).toHaveCount(expected.length);
      for (const entry of expected) {
        const row = group.locator("tr.battery-case").filter({
          has: page.locator("td:first-child", { hasText: entry.name }),
        });
        await expect(row).toHaveCount(1);
        await expect(row).toBeVisible();
        if (entry.status === "caught") {
          await expect(row.locator("td").nth(1)).toHaveText(entry.matched_test!);
          await expect(row.locator("td").nth(2)).toHaveText("Caught");
        } else {
          await expect(row.locator("td").nth(2)).not.toHaveText("Caught");
        }
      }
    }
  });
});

test("a group can be collapsed and reopened once the page has hydrated", async ({ page }) => {
  await page.goto("/mutation-battery", { waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveAttribute("data-hydrated", "true");
  await expect(page.locator("tr.battery-case")).toHaveCount(battery.total);

  const group = page.locator("details.battery-group").first();
  const inGroup = group.locator("tr.battery-case");
  const count = await inGroup.count();
  await expect(inGroup.first()).toBeVisible();

  await group.locator("summary").click();
  await expect(group).not.toHaveAttribute("open", "");
  await expect(inGroup.first()).toBeHidden();
  // Collapsing hides rows; it does not remove them, and no other group moves.
  await expect(inGroup).toHaveCount(count);
  await expect(page.locator("tr.battery-case")).toHaveCount(battery.total);

  await group.locator("summary").click();
  await expect(group).toHaveAttribute("open", "");
  await expect(inGroup.first()).toBeVisible();
});

test("the battery is reachable from the safety page, quotes the same count, and links back", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveAttribute("data-hydrated", "true");
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("button", { name: "Safety" })
    .click();
  await expect(page.locator(".mutation-score strong")).toHaveText(
    `${battery.caught} / ${battery.total}`,
  );

  await page.getByRole("link", { name: /See every injected case/ }).click();
  await expect(page).toHaveURL(/\/mutation-battery$/);
  await expect(page.locator("tr.battery-case")).toHaveCount(battery.total);
  await expect(page.locator("html")).toHaveAttribute("data-hydrated", "true");

  // The battery is a child of Safety, so that is the nav entry that is lit,
  // and the verification banner is still above the page.
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  await expect(nav.getByRole("button", { name: "Safety" })).toHaveAttribute("aria-current", "page");
  const banner = page.getByRole("note", { name: "Verification disclaimer" });
  await expect(banner).toBeVisible();
  await expect(banner).toContainText(VERIFY_COMMAND);
  await expect(banner.getByRole("button")).toHaveCount(1);

  await page.getByRole("button", { name: "Back to the safety page" }).click();
  await expect(page).toHaveURL(/\/#safety$/);
  await expect(page.getByRole("heading", { name: /The refusal path/ })).toBeVisible();
});

test("the battery fits a phone-width screen without sideways scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/mutation-battery", { waitUntil: "domcontentloaded" });
  await expect(page.locator("html")).toHaveAttribute("data-hydrated", "true");
  await expect(page.locator("tr.battery-case")).toHaveCount(battery.total);
  await expect(page.locator("tr.battery-case").first()).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});
