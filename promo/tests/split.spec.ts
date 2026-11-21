import { test, expect } from "@playwright/test";

test("the front page leads to each long read, and each page has its section", async ({ page }) => {
  await page.goto("/");
  for (const [href, id] of [["./crows.html", "poe"], ["./app.html", "app"], ["./cawscout.html", "cawscout"], ["./cawdex.html", "cawdex"]]) {
    await expect(page.locator(`main a[href="${href}"]`).first()).toBeVisible();
    await page.goto(href.replace("./", "/"));
    await expect(page.locator(`#${id} h1`)).toBeVisible();
    await page.goto("/");
  }
});

test("an old link to a moved section follows it to its new page", async ({ page }) => {
  await page.goto("/#results");
  await expect(page).toHaveURL(/\/cawdex\.html#results$/);
  await expect(page.locator("#auc-chart > *").first()).toBeVisible();
});

test("an anchor still on the front page stays there", async ({ page }) => {
  await page.goto("/#cawscout");
  await expect(page).toHaveURL(/\/#cawscout$/);
});
