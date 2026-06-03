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

  // Draft-on-login: the stakeholder lands straight in the draft welcome state with
  // the AI greeting and input ready — no "New Session" click. Sending the first
  // message creates and auto-names the session.
  await page.getByPlaceholder(/Describe what you want/).fill("I want a payment app for online retail.");
  await page.getByRole("button", { name: "Send" }).click();

  // The greeting is itself an agent turn, so waiting for the *first* agent bubble
  // would pass without Gemini ever responding. Wait for the second one — the
  // actually-generated probing question — to prove the question loop ran.
  await expect
    .poll(() => page.locator("[data-role=agent]").count(), { timeout: 45_000 })
    .toBeGreaterThanOrEqual(2);

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: ".md" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.md$/);
});
