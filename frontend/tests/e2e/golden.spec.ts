import { test, expect } from "@playwright/test";

const uniqueEmail = () => `e2e_${Date.now()}@example.com`;

// Golden-path smoke test against the running stack (docker compose up -d).
// Covers signup through the real API, JWT auth, role-based redirect, and the
// stakeholder landing state. The interview/Gemini path needs an RE-created
// project and invite (promotion is an ops script by design), so it is out of
// scope for this self-contained spec.
test("signup -> land in stakeholder view with project empty state", async ({ page }) => {
  const email = uniqueEmail();

  await page.goto("/signup");
  await page.getByPlaceholder("you@company.com").fill(email);
  await page.getByPlaceholder("••••••••").fill("Passw0rd!");
  await page.getByPlaceholder("Jane Doe").fill("E2E Tester");
  await page.getByRole("button", { name: "Create account" }).click();

  // RoleRedirect sends fresh stakeholders to /chat; without a project the
  // composer renders the select-a-project notice.
  await expect(page.getByText("Select a project to start the interview.")).toBeVisible({
    timeout: 15_000,
  });
  await expect(page).toHaveURL(/\/chat$/);
});
