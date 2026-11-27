import { expect, test } from "@playwright/test";

test("the replay page shows an edit, takes a prediction and reveals recorded answers", async ({ page }) => {
  let modelCalls = 0;
  await page.route("**/api/v1/**", (route) => {
    modelCalls += 1;
    return route.abort();
  });
  await page.goto("/replay");

  await expect(page.getByRole("heading", { name: "Does the answer follow the filing?" })).toBeVisible();
  await page.getByRole("tab", { name: /Target figure changed/ }).click();
  await expect(page.getByText(/Synthetic edit for testing/)).toBeVisible();
  await expect(page.getByLabel("Filing excerpt").locator("mark").first()).toBeVisible();

  await page.getByRole("tab", { name: /Evidence removed/ }).click();
  await page.getByRole("button", { name: "Say it can't answer" }).click();
  await expect(page.getByText(/Expected: Say the evidence is insufficient/)).toBeVisible();
  await expect(page.getByText("Current prompt")).toBeVisible();

  expect(modelCalls).toBe(0);
});
