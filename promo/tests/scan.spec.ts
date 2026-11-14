import { test, expect, type Page } from "@playwright/test";

const api = "https://field.crowgpt.org";
const headers = { "Access-Control-Allow-Origin": "*" };
const config = {
  kinds: { photo: true, audio: true, video: true },
  formats: { photo: ["jpg", "png"], audio: ["wav", "mp3"], video: ["mp4"] },
  max_mb: { photo: 15, audio: 40, video: 40 },
  sound_seconds: 90,
  turnstile_site_key: "public-key",
  turnstile_required: true,
};
const photoResult = {
  ranking: [
    { slug: "american-crow", common_name: "American Crow", scientific_name: "Corvus brachyrhynchos", probability: 0.9 },
    { slug: "common-raven", common_name: "Common Raven", scientific_name: "Corvus corax", probability: 0.1 },
  ],
  bird_box: { left: 10, top: 10, right: 50, bottom: 40, birds: 1 },
  used_location: true, latitude: 40.76, longitude: -111.89, width: 64, height: 48,
};
const soundResult = {
  duration_sec: 12, truncated: false, located: false,
  waveform: Array.from({ length: 120 }, (_, i) => Math.abs(Math.sin(i / 5))),
  calls: [
    { start: 0, end: 3, species: "American Crow", scientific_name: "Corvus brachyrhynchos",
      call_type: "alarm call", confidence: 0.97, crow_conf: 0.9, candidate: false },
    { start: 6, end: 9, species: "Common Raven", scientific_name: "Corvus corax",
      call_type: null, confidence: null, crow_conf: 0.4, candidate: true },
  ],
};
// A 1x1 PNG, so the photo result has a picture to draw the box on.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

async function setup(page: Page, overrides: Record<string, unknown> = {}, result: unknown = photoResult) {
  const posts: string[] = [];
  await page.route(`${api}/api/demo/scan`, async route => {
    if (route.request().method() === "GET") {
      return route.fulfill({ headers, json: { ...config, ...overrides } });
    }
    posts.push(route.request().postData() ?? "");
    return route.fulfill({ status: 202, headers, json: { id: "abc", kind: "photo", state: "queued", ahead: 0 } });
  });
  await page.route(`${api}/api/demo/scan/abc`, route => route.fulfill({
    headers, json: { id: "abc", kind: "photo", state: "done", result },
  }));
  await page.route("https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit", route =>
    route.fulfill({ contentType: "application/javascript", body: `
      window.__challenge = {};
      window.turnstile = {
        render(container, options) { window.__challenge.options = options; return 'scan'; },
        reset() { window.__challenge.resets = (window.__challenge.resets || 0) + 1; },
        remove() {}
      };
    ` }));
  await page.goto("/scan.html");
  return posts;
}

async function solve(page: Page) {
  await page.waitForFunction(() => (window as any).__challenge?.options);
  await page.evaluate(() => (window as any).__challenge.options.callback("single-use-token"));
}

test("a photo is uploaded with a scan-action token and comes back named", async ({ page }) => {
  const posts = await setup(page);
  await expect(page.locator("#scan-drop")).toHaveClass(/is-disabled/);
  await solve(page);
  expect(await page.evaluate(() => (window as any).__challenge.options.action)).toBe("demo-scan");
  await page.locator("#scan-picker").setInputFiles({ name: "crow.png", mimeType: "image/png", buffer: PNG });
  await expect(page.locator(".scan-answer h3")).toHaveText("American Crow");
  await expect(page.locator(".scan-box")).toBeVisible();
  await expect(page.locator(".scan-ranking li")).toHaveCount(2);
  expect(posts[0]).toContain("single-use-token");
  await page.screenshot({ path: "test-results/scan-photo.png", fullPage: true });
});

test("a recording comes back as a timeline with its calls listed", async ({ page }) => {
  await setup(page, {}, soundResult);
  await solve(page);
  await page.locator("#scan-picker").setInputFiles({ name: "dawn.wav", mimeType: "audio/wav", buffer: Buffer.from("RIFF") });
  await expect(page.locator(".scan-timeline")).toBeVisible();
  await expect(page.locator(".scan-call")).toHaveCount(2);
  await expect(page.locator(".scan-call").first()).toContainText("Alarm call · American Crow");
  await expect(page.locator(".scan-call").nth(1)).toContainText("maybe a corvid");
  await expect(page.locator(".scan-legend li")).toHaveCount(2);
  await expect(page.locator(".scan-sound")).toContainText("unfiltered guess");
  await page.screenshot({ path: "test-results/scan-sound.png", fullPage: true });
});

test("a kind with no worker is named as unavailable and refused in the browser", async ({ page }) => {
  await setup(page, { kinds: { photo: false, audio: true, video: true } });
  await solve(page);
  await expect(page.locator("#scan-limits")).toContainText("Not available right now: photo");
  await page.locator("#scan-picker").setInputFiles({ name: "crow.png", mimeType: "image/png", buffer: PNG });
  await expect(page.locator("#scan-status")).toContainText("cannot read crow.png");
});

test("the public page stays off when the server has no verification key", async ({ page }) => {
  await setup(page, { turnstile_site_key: null, turnstile_required: false });
  await expect(page.locator("#scan-status")).toContainText("Verification is unavailable");
});

test("an unreachable server leaves the page readable", async ({ page }) => {
  await page.route(`${api}/api/demo/scan`, route => route.abort());
  await page.goto("/scan.html");
  await expect(page.locator("h1")).toHaveText("Scan a crow");
  await expect(page.locator("#scan-status")).toContainText("offline");
});
