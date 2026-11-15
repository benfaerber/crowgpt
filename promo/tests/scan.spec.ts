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
  used_location: true, latitude: 40.76, longitude: -111.89, location_source: "given",
  width: 64, height: 48,
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

const geo = { latitude: 40.76, longitude: -111.89, city: "Salt Lake City", region: "Utah", country: "US" };

async function setup(page: Page, overrides: Record<string, unknown> = {}, result: unknown = photoResult,
                     whereabouts: unknown = geo) {
  const posts: string[] = [];
  await page.route("**/geo", route => whereabouts
    ? route.fulfill({ json: whereabouts })
    : route.fulfill({ status: 404, body: "not found" }));
  await page.route(`${api}/api/demo/scan`, async route => {
    if (route.request().method() === "GET") {
      return route.fulfill({ headers, json: { ...config, ...overrides } });
    }
    // The token rides in a header so the server can check it before the file.
    posts.push(`${route.request().headers()["x-turnstile-token"] ?? ""}\n${route.request().postData() ?? ""}`);
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
  expect(posts[0].split("\n")[0]).toBe("single-use-token");
  expect(posts[0]).toContain("40.76");
  await expect(page.locator(".scan-answer")).toContainText("Your approximate location was used");
  await page.screenshot({ path: "test-results/scan-photo.png", fullPage: true });
});

test("the wait counts down, and says so when it runs over", async ({ page }) => {
  await setup(page);
  let polls = 0;
  await page.route(`${api}/api/demo/scan`, async route => route.request().method() === "GET"
    ? route.fallback()
    : route.fulfill({ status: 202, headers, json: { id: "abc", kind: "photo", state: "queued", ahead: 1, eta_seconds: 75 } }));
  await page.route(`${api}/api/demo/scan/abc`, route => {
    polls += 1;
    if (polls === 1) return route.fulfill({ headers, json: { id: "abc", kind: "photo", state: "running", ahead: 0, eta_seconds: 3 } });
    if (polls < 5) return route.fulfill({ headers, json: { id: "abc", kind: "photo", state: "running", ahead: 0, eta_seconds: 0 } });
    return route.fallback();
  });
  await solve(page);
  await page.locator("#scan-picker").setInputFiles({ name: "crow.png", mimeType: "image/png", buffer: PNG });
  const status = page.locator("#scan-status");
  await expect(status).toContainText("1 ahead of you in the queue… About 2 minutes left.");
  await expect(status).toContainText(/Looking at the photo… About [123] seconds? left\./);
  await expect(status).toContainText("Looking at the photo… Taking longer than usual, still working.");
  await expect(page.locator(".scan-eta")).toHaveAttribute("aria-hidden", "true");
  // The answer follows the loader's landing and caw, about two seconds more.
  await expect(page.locator(".scan-answer h3")).toHaveText("American Crow", { timeout: 10000 });
  await expect(status).not.toContainText("still working");
});

test("a file is only offered for keeping when its box is ticked, and the box resets", async ({ page }) => {
  const posts = await setup(page, {}, photoResult, { ...geo, city: "Toronto", region: "Ontario", country: "CA" });
  await page.route(`${api}/api/demo/scan/abc`, route => route.fulfill({
    headers, json: { id: "abc", kind: "photo", state: "done", result: photoResult, kept: true },
  }));
  await expect(page.locator("#scan-keep")).not.toBeChecked();
  await solve(page);
  await page.locator("#scan-keep").check();
  await page.locator("#scan-picker").setInputFiles({ name: "crow.png", mimeType: "image/png", buffer: PNG });
  await expect(page.locator(".scan-kept")).toContainText("Kept for the project");
  await expect(page.locator("#scan-keep")).not.toBeChecked();
  expect(posts[0]).toContain('name="keep"');
  await solve(page);
  await page.locator("#scan-picker").setInputFiles({ name: "crow.png", mimeType: "image/png", buffer: PNG });
  await expect(page.locator(".scan-result")).toHaveCount(2);
  expect(posts[1]).not.toContain('name="keep"');
  await expect(page.locator(".scan-kept")).toHaveCount(1);
});

test("a photo of a cat is called a cat, and a photo with no bird says so", async ({ page }) => {
  await setup(page, {}, { ...photoResult, bird_box: null, verdict: "other", instead: "cat" });
  await solve(page);
  await page.locator("#scan-picker").setInputFiles({ name: "cat.png", mimeType: "image/png", buffer: PNG });
  await expect(page.locator(".scan-answer h3")).toHaveText("Not a corvid");
  await expect(page.locator(".scan-answer")).toContainText("a photo of a cat");
  await expect(page.locator(".scan-ranking")).toHaveCount(0);
  await expect(page.locator(".scan-box")).toHaveCount(0);

  await page.route(`${api}/api/demo/scan/abc`, route => route.fulfill({
    headers, json: { id: "abc", kind: "photo", state: "done", result: { ...photoResult, bird_box: null, verdict: "no_bird", instead: null } },
  }));
  await solve(page);
  await page.locator("#scan-picker").setInputFiles({ name: "sky.png", mimeType: "image/png", buffer: PNG });
  await expect(page.locator(".scan-answer h3").first()).toHaveText("No bird found");
  await expect(page.locator(".scan-answer").first()).toContainText("the closest match is American Crow");
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

test("the visitor's approximate location is shown, and left out when unticked", async ({ page }) => {
  const posts = await setup(page);
  await expect(page.locator("#scan-place")).toHaveText("near Salt Lake City, Utah");
  await page.locator("#scan-locate").uncheck();
  await solve(page);
  await page.locator("#scan-picker").setInputFiles({ name: "crow.png", mimeType: "image/png", buffer: PNG });
  await expect(page.locator(".scan-answer h3")).toBeVisible();
  expect(posts[0]).not.toContain("latitude");
});

test("with no location to offer, the page offers none and sends none", async ({ page }) => {
  const posts = await setup(page, {}, photoResult, null);
  await solve(page);
  await expect(page.locator("#scan-locate-row")).toBeHidden();
  await page.locator("#scan-picker").setInputFiles({ name: "crow.png", mimeType: "image/png", buffer: PNG });
  await expect(page.locator(".scan-answer h3")).toBeVisible();
  expect(posts[0]).not.toContain("latitude");
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

test("a refused upload says why, and the sentence stays after the check resets", async ({ page }) => {
  await setup(page);
  await page.unroute(`${api}/api/demo/scan`);
  await page.route(`${api}/api/demo/scan`, route => route.request().method() === "GET"
    ? route.fulfill({ headers, json: config })
    : route.fulfill({ status: 429, headers, contentType: "text/html",
        body: "<!doctype html><title>429</title><h1>Too Many Requests</h1><p>that is enough scans for one hour from one address</p>" }));
  await page.reload();
  await solve(page);
  await page.locator("#scan-picker").setInputFiles({ name: "crow.png", mimeType: "image/png", buffer: PNG });
  const status = page.locator("#scan-status");
  await expect(status).toHaveText("That is enough scans for one hour from one address");
  await page.waitForTimeout(500);
  await expect(status).toBeVisible();
  await expect(status).toHaveText("That is enough scans for one hour from one address");
});

test("a scan that fails on the server leaves a card saying why", async ({ page }) => {
  await setup(page);
  await page.unroute(`${api}/api/demo/scan/abc`);
  await page.route(`${api}/api/demo/scan/abc`, route => route.fulfill({
    headers, json: { id: "abc", kind: "video", state: "failed", error: "This video has no sound, so there is nothing to listen to." },
  }));
  await solve(page);
  await page.locator("#scan-picker").setInputFiles({ name: "walk.mp4", mimeType: "video/mp4", buffer: PNG });
  const card = page.locator(".scan-result-failed");
  await expect(card).toContainText("walk.mp4");
  await expect(card).toContainText("This video has no sound");
});

test("in the US the keep box starts ticked and stays ticked from file to file", async ({ page }) => {
  const posts = await setup(page);
  await page.route(`${api}/api/demo/scan/abc`, route => route.fulfill({
    headers, json: { id: "abc", kind: "photo", state: "done", result: photoResult, kept: true },
  }));
  await expect(page.locator("#scan-keep")).toBeChecked();
  await solve(page);
  await page.locator("#scan-picker").setInputFiles({ name: "crow.png", mimeType: "image/png", buffer: PNG });
  await expect(page.locator(".scan-kept")).toContainText("Kept for the project");
  expect(posts[0]).toContain('name="keep"');
  await expect(page.locator("#scan-keep")).toBeChecked();
});

test("a US visitor who unticks the keep box is not ticked again", async ({ page }) => {
  const posts = await setup(page);
  await expect(page.locator("#scan-keep")).toBeChecked();
  await page.locator("#scan-keep").uncheck();
  await solve(page);
  await page.locator("#scan-picker").setInputFiles({ name: "crow.png", mimeType: "image/png", buffer: PNG });
  await expect(page.locator(".scan-result")).toHaveCount(1, { timeout: 10000 });
  expect(posts[0]).not.toContain('name="keep"');
  await expect(page.locator("#scan-keep")).not.toBeChecked();
});
