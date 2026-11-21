import { expect, test } from "@playwright/test";

const answerBody = {
  answer: "3M's capital expenditure in fiscal 2018 was $1,577 million.",
  sources: [
    {
      text: "Purchases of property, plant and equipment (PP&E) (1,577) (1,373)",
      source: "3M_2018_10K",
      company: "3M",
      year: "2018",
      section: "Cash flow",
      score: 2.37,
    },
  ],
  latency_ms: 420,
  cached: false,
  sub_questions: null,
};

test("asking a question shows the answer and a highlighted source", async ({ page }) => {
  await page.route("**/api/v1/query", (route) => route.fulfill({ json: answerBody }));
  await page.goto("/");
  await page.getByLabel("Question about SEC 10-K filings").fill("What was 3M's capex in 2018?");
  await page.getByRole("button", { name: "Ask" }).click();

  await expect(page.getByText("$1,577 million")).toBeVisible();
  await page.getByRole("button", { name: /3M/ }).click();
  await expect(page.locator("mark", { hasText: "1,577" }).first()).toBeVisible();
});

test("a rate-limited response disables Ask and shows a countdown", async ({ page }) => {
  await page.route("**/api/v1/query", (route) =>
    route.fulfill({
      status: 429,
      headers: { "Retry-After": "30" },
      json: { detail: "Rate limited" },
    }),
  );
  await page.goto("/");
  await page.getByLabel("Question about SEC 10-K filings").fill("Anything");
  await page.getByRole("button", { name: "Ask" }).click();

  // Next.js adds its own route-announcer alert, so match ours by text.
  await expect(page.getByRole("alert").filter({ hasText: "Rate limited" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Retry in \d+s/ })).toBeDisabled();
});

test("an abstaining answer explains why", async ({ page }) => {
  await page.route("**/api/v1/query", (route) =>
    route.fulfill({
      json: {
        ...answerBody,
        answer: "Insufficient context to answer this question accurately.",
        sources: [],
      },
    }),
  );
  await page.goto("/");
  await page.getByLabel("Question about SEC 10-K filings").fill("Unanswerable");
  await page.getByRole("button", { name: "Ask" }).click();

  await expect(page.getByText(/could not find this in the retrieved passages/)).toBeVisible();
});
