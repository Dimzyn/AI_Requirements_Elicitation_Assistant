import { test, expect } from "@playwright/test";

const uniqueEmail = () => `e2e_${Date.now()}@example.com`;

test("signup -> create session -> ask -> see probing question -> export", async ({ page }) => {
  const email = uniqueEmail();

  await page.goto("/signup");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password").fill("Passw0rd!");
  await page.getByPlaceholder("Real name for future operation").fill("E2E Tester");
  await page.getByRole("button", { name: "Sign up" }).click();

  await expect(page.getByRole("heading", { name: /AI Probing Question Generator/i })).toBeVisible();

  await page.getByRole("button", { name: "New Session" }).click();
  await page.getByPlaceholder("Project title").fill("E2E Payments");
  await page.getByRole("button", { name: "Create" }).click();

  await page.getByPlaceholder(/Describe what you want/).fill("I want a payment app for online retail.");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.locator("[data-role=agent]").first()).toBeVisible({ timeout: 45_000 });

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: ".md" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.md$/);
});
