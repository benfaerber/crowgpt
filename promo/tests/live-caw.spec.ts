import { test, expect, type Page } from "@playwright/test";

const api = "https://field.crowgpt.org";
const menu = { items: [{ key: "caw", label: "A caw", model: "crowgpt2", call_type: null }],
  turnstile_site_key: "public-key" };
const headers = { "Access-Control-Allow-Origin": "*" };

async function setup(page: Page, options: { apiDown?: boolean; widgetDown?: boolean } = {}) {
  await page.route(`${api}/api/demo/menu`, route => route.fulfill({
    status: options.apiDown ? 503 : 200, headers, json: menu,
  }));
  await page.route("https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit", route => {
    if (options.widgetDown) return route.abort();
    return route.fulfill({ contentType: "application/javascript", body: `
      window.__challenge = {};
      window.turnstile = {
        render(container, options) { window.__challenge.options = options; return 'demo'; },
        reset() { window.__challenge.resets = (window.__challenge.resets || 0) + 1; },
        remove() { window.__challenge.removed = true; }
      };
    ` });
  });
  await page.goto("/");
}

async function solve(page: Page, token = "single-use-token") {
  await page.waitForFunction(() => (window as any).__challenge?.options);
  await page.evaluate(token => (window as any).__challenge.options.callback(token), token);
}

for (const outage of ["apiDown", "widgetDown"] as const) {
  test(`${outage}: static page still renders with demo hidden`, async ({ page }) => {
    await setup(page, { [outage]: true });
    await expect(page.locator("h1")).toBeVisible();
    await expect(page.locator("#live-caw")).toBeHidden();
    await expect(page.locator('form[action*="/preview/request"]')).toBeVisible();
  });
}

test("buttons wait for verification; each press sends a new token", async ({ page }) => {
  const tokens: string[] = [];
  await page.route(`${api}/api/demo/generate/caw`, route => {
    tokens.push(new URLSearchParams(route.request().postData() || "").get("cf-turnstile-response") || "");
    return route.fulfill({ headers, json: { id: 1, state: "done", seed: 42, model: "crowgpt2", clip: "/api/demo/clips/1" } });
  });
  await page.route(`${api}/api/demo/clips/1`, route => route.fulfill({ status: 204, headers }));
  await setup(page);
  await expect(page.locator(".live-caw-menu")).toBeHidden();
  await solve(page, "first-token");
  const button = page.getByRole("button", { name: "A caw", exact: true });
  await expect(button).toBeEnabled();
  await button.click();
  await expect(page.locator(".live-caw-result")).toContainText("seed 42");
  await expect(button).toBeDisabled();
  await solve(page, "second-token");
  await button.click();
  await expect.poll(() => tokens).toEqual(["first-token", "second-token"]);
  expect(await page.evaluate(() => (window as any).__challenge.options.action)).toBe("demo-generate");
});

test("expired verification hides the buttons until renewed", async ({ page }) => {
  await setup(page);
  await solve(page);
  await page.evaluate(() => (window as any).__challenge.options["expired-callback"]());
  await expect(page.locator(".live-caw-menu")).toBeHidden();
  await solve(page, "fresh-token");
  await expect(page.locator(".live-caw-button")).toBeEnabled();
});

test("verification/API failure on a press hides only the optional demo", async ({ page }) => {
  await page.route(`${api}/api/demo/generate/caw`, route => route.fulfill({ status: 503, headers }));
  await setup(page);
  await solve(page);
  await page.locator(".live-caw-button").click();
  await expect(page.locator("#live-caw")).toBeHidden();
  await expect(page.locator("h1")).toBeVisible();
});

test("rate refusal is shown without retrying the generation", async ({ page }) => {
  let attempts = 0;
  await page.route(`${api}/api/demo/generate/caw`, route => {
    attempts++;
    return route.fulfill({ status: 429, headers });
  });
  await setup(page);
  await solve(page);
  await page.locator(".live-caw-button").click();
  await expect(page.locator(".live-caw-result")).toContainText("Too many requests");
  expect(attempts).toBe(1);
});
