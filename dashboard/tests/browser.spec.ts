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
  await expect(page.getByText("Structural inspection complete")).toBeVisible();
  await expect(page.getByText(/Trusted verification was not performed/)).toBeVisible();

  await page.getByRole("button", { name: /Canonical pinned local battery/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute("aria-modal", "true");
  await expect(
    dialog.getByRole("button", { name: "Close evidence details" }),
  ).toBeFocused();
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
