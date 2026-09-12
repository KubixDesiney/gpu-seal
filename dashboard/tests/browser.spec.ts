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
