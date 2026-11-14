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
  await page.goto("/crowgpt.html");
}

async function solve(page: Page, token = "single-use-token") {
  await page.waitForFunction(() => (window as any).__challenge?.options);
  await page.evaluate(token => (window as any).__challenge.options.callback(token), token);
}

const chip = (page: Page) => page.getByRole("button", { name: "A caw", exact: true });

for (const outage of ["apiDown", "widgetDown"] as const) {
  test(`${outage}: the chat says it is offline and offers nothing to press`, async ({ page }) => {
    await setup(page, { [outage]: true });
    await expect(page.locator("h1")).toBeVisible();
    await expect(page.locator("#chat-presence")).toContainText("offline");
    await expect(page.locator(".chat-chip")).toHaveCount(0);
  });
}

test("the front page links to the chat instead of generating itself", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".chat-invite")).toHaveAttribute("href", "./crowgpt.html");
  await expect(page.locator("#crowgpt-preview audio")).toHaveCount(3);
});

test("chips wait for verification; each press sends a new token", async ({ page }) => {
  const tokens: string[] = [];
  await page.route(`${api}/api/demo/generate/caw`, route => {
    tokens.push(new URLSearchParams(route.request().postData() || "").get("cf-turnstile-response") || "");
    return route.fulfill({ headers, json: { id: 1, state: "done", seed: 42, model: "crowgpt2", clip: "/api/demo/clips/1" } });
  });
  await page.route(`${api}/api/demo/clips/1`, route => route.fulfill({ status: 204, headers }));
  await setup(page);
  await expect(chip(page)).toBeDisabled();
  await solve(page, "first-token");
  await expect(chip(page)).toBeEnabled();
  await chip(page).click();
  await expect(page.locator(".chat-bubble-me")).toHaveCount(1);
  await expect(page.locator(".chat-thread")).toContainText("seed 42");
  await expect(page.locator(".voice-note")).toHaveCount(1);
  await expect(chip(page)).toBeDisabled();
  await solve(page, "second-token");
  await chip(page).click();
  await expect.poll(() => tokens).toEqual(["first-token", "second-token"]);
  expect(await page.evaluate(() => (window as any).__challenge.options.action)).toBe("demo-generate");
});

test("a queued request shows CrowGPT typing until the clip is done", async ({ page }) => {
  let polls = 0;
  await page.route(`${api}/api/demo/generate/caw`, route =>
    route.fulfill({ headers, json: { id: 7, state: "queued", seed: 9, model: "crowgpt2", ahead: 2 } }));
  await page.route(`${api}/api/demo/generations/7`, route => {
    polls++;
    return route.fulfill({ headers, json: { id: 7, state: "done", seed: 9, model: "crowgpt2", clip: "/api/demo/clips/7" } });
  });
  await page.route(`${api}/api/demo/clips/7`, route => route.fulfill({ status: 204, headers }));
  await setup(page);
  await solve(page);
  await chip(page).click();
  await expect(page.locator(".chat-typing-label")).toContainText("2 ahead of you");
  await expect(page.locator(".chat-thread")).toContainText("seed 9", { timeout: 10000 });
  await expect(page.locator(".chat-typing")).toHaveCount(0);
  expect(polls).toBe(1);
});

test("expired verification disables the chips until renewed", async ({ page }) => {
  await setup(page);
  await solve(page);
  await page.evaluate(() => (window as any).__challenge.options["expired-callback"]());
  await expect(chip(page)).toBeDisabled();
  await solve(page, "fresh-token");
  await expect(chip(page)).toBeEnabled();
});

test("an API failure on a press takes the chat offline, not the page", async ({ page }) => {
  await page.route(`${api}/api/demo/generate/caw`, route => route.fulfill({ status: 503, headers }));
  await setup(page);
  await solve(page);
  await chip(page).click();
  await expect(page.locator("#chat-presence")).toContainText("offline");
  await expect(page.locator(".chat-chip")).toHaveCount(0);
  await expect(page.locator("h1")).toBeVisible();
});

test("rate refusal is said in the chat without retrying", async ({ page }) => {
  let attempts = 0;
  await page.route(`${api}/api/demo/generate/caw`, route => {
    attempts++;
    return route.fulfill({ status: 429, headers });
  });
  await setup(page);
  await solve(page);
  await chip(page).click();
  await expect(page.locator(".chat-thread")).toContainText("a lot of crow for one hour");
  expect(attempts).toBe(1);
  await solve(page, "next-token");
  await expect(chip(page)).toBeEnabled();
});
