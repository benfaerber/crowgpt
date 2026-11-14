/** Ask CrowGPT yourself: the one thing on the page that talks to a server.
 *
 * The field server keeps a shelf of clips generated ahead, so a press usually
 * plays at once; when the shelf for an item is bare the press becomes a live
 * job and this polls until the bout is done. Each press sends a single-use
 * Turnstile token for server verification; no secret lives on the page. Buttons
 * stay hidden until the API and widget are ready. The static page always works.
 *
 * The copy a field server serves at /promo is pressed without a token when
 * that server has no Turnstile key and does not require one, which is what a
 * local `make field` is; a page that hid itself there could never be tried.
 * The public build never does this: on crowgpt.org a server without a key
 * means the buttons stay hidden.
 */

import { Player } from "./caw-player";
import { el } from "./dom";
import { DemoChallenge } from "./demo-challenge";

interface MenuItem {
  key: string;
  label: string;
  model: string;
  call_type: string | null;
}

interface Generation {
  id: number;
  state: "queued" | "running" | "done" | "failed";
  seed: number;
  model: string;
  call_type: string | null;
  duration_sec?: number;
  clip?: string;
  ahead?: number;
  error?: string;
}

const POLL_MS = 3000;

export class LiveCaw {
  private readonly root: HTMLElement | null;
  private readonly menu: HTMLElement | null;
  private readonly result: HTMLElement | null;
  private readonly buttons: HTMLButtonElement[] = [];
  private polling = 0;
  private token = "";
  private busy = false;
  private unavailable = false;
  private verified = true;
  private readonly challenge = new DemoChallenge();

  private fetch(path: string, options?: RequestInit): Promise<Response> {
    return fetch(`${this.api}${path}`, { ...options, signal: AbortSignal.timeout(10000) });
  }

  constructor(
    selector: string,
    private readonly api: string,
  ) {
    this.root = document.querySelector(selector);
    this.menu = this.root?.querySelector(".live-caw-menu") ?? null;
    this.result = this.root?.querySelector(".live-caw-result") ?? null;
  }

  async mount(): Promise<void> {
    if (!this.root || !this.menu || !this.result) return;
    let items: MenuItem[];
    let siteKey: string | undefined;
    // The menu is the health check: it answers only from a server that is up,
    // and it is the one route that carries the CORS header — /api/health does
    // not, so a separate probe of it is blocked by the browser on crowgpt.org
    // and read as "down". That is how the block shipped hidden on 2026-10-31.
    try {
      const menu = await this.fetch("/api/demo/menu");
      if (!menu.ok) return;
      const body = (await menu.json()) as {
        items: MenuItem[];
        turnstile_site_key?: string | null;
        turnstile_required?: boolean;
      };
      const unverifiedAllowed = this.api === "" && !body.turnstile_required;
      if (!body.turnstile_site_key && !unverifiedAllowed) return;
      items = body.items;
      siteKey = body.turnstile_site_key ?? undefined;
    } catch {
      return;
    }
    this.verified = siteKey !== undefined;
    this.menu.hidden = this.verified;
    for (const item of items) {
      const button = el("button", {
        className: "button live-caw-button",
        text: item.label,
        attrs: { type: "button", "data-key": item.key },
      });
      button.addEventListener("click", () => void this.press(item, button));
      this.buttons.push(button);
      this.menu.append(button);
    }
    this.root.hidden = false;
    if (siteKey === undefined) {
      this.setBusy(null);
      return;
    }
    const widget = el("div", { className: "live-caw-verification" });
    this.root.insertBefore(widget, this.menu);
    try {
      await this.challenge.mount(widget, siteKey, token => {
        this.token = token;
        if (this.menu) this.menu.hidden = !token || this.unavailable;
        if (!this.busy) this.setBusy(null);
      }, () => this.hide());
    } catch {
      this.hide();
    }
  }

  private async press(item: MenuItem, button: HTMLButtonElement): Promise<void> {
    if (!this.ready() || this.busy) return;
    const token = this.token;
    this.token = ""; // A Siteverify token is single-use, including failed requests.
    this.stopPolling();
    this.setBusy(button);
    this.say("Asking…");
    let generation: Generation;
    try {
      const response = await this.fetch(`/api/demo/generate/${item.key}`, {
        method: "POST",
        body: new URLSearchParams(token ? { "cf-turnstile-response": token } : {}),
      });
      if (response.status === 429) {
        this.say("Too many requests just now. Please try again later.");
        this.setBusy(null);
        this.challenge.reset();
        return;
      }
      if (response.status === 503) {
        this.hide();
        return;
      }
      if (!response.ok) throw new Error(`${response.status}`);
      generation = (await response.json()) as Generation;
    } catch {
      this.hide();
      return;
    }
    this.challenge.reset();
    this.follow(item, generation);
  }

  private follow(item: MenuItem, generation: Generation): void {
    if (generation.state === "done") {
      this.play(item, generation);
      this.setBusy(null);
      return;
    }
    if (generation.state === "failed") {
      this.say("That one failed on the server. Try another press.");
      this.setBusy(null);
      return;
    }
    const ahead = generation.ahead ?? 0;
    this.say(
      ahead === 0
        ? `Generating a fresh one — about half a minute. Seed ${generation.seed}.`
        : `Generating — ${ahead} ahead of you in the queue. Seed ${generation.seed}.`,
    );
    this.polling = window.setTimeout(() => void this.poll(item, generation.id), POLL_MS);
  }

  private async poll(item: MenuItem, id: number): Promise<void> {
    try {
      const response = await this.fetch(`/api/demo/generations/${id}`);
      if (!response.ok) throw new Error(`${response.status}`);
      this.follow(item, (await response.json()) as Generation);
    } catch {
      this.hide();
    }
  }

  private play(item: MenuItem, generation: Generation): void {
    if (!this.result) return;
    const audio = el("audio", {
      attrs: { controls: "", preload: "auto", src: `${this.api}${generation.clip}` },
    });
    const caption = el("figcaption", {
      text: `${item.model === "crowgpt2" ? "CrowGPT2" : "CrowGPT"}: ${item.label.toLowerCase()}, generated, seed ${generation.seed}`,
    });
    const figure = el("figure", { className: "caw-player caw-player-bot" }, caption, audio);
    this.result.replaceChildren(figure);
    new Player(figure, audio).mount();
    // Inside the click's grace period this plays; after a poll the browser may
    // refuse, and the player is right there to press.
    void audio.play().catch(() => undefined);
  }

  private say(text: string): void {
    this.result?.replaceChildren(el("p", { className: "live-caw-status", text }));
  }

  private setBusy(active: HTMLButtonElement | null): void {
    this.busy = active !== null;
    for (const button of this.buttons) {
      button.disabled = this.busy || !this.ready();
      button.classList.toggle("is-asking", button === active);
    }
  }

  private ready(): boolean {
    return !this.unavailable && (!this.verified || this.token !== "");
  }

  private hide(): void {
    this.unavailable = true;
    this.stopPolling();
    this.token = "";
    if (this.root) this.root.hidden = true;
    // An error callback may run inside render(), before the widget id returns.
    queueMicrotask(() => this.challenge.remove());
  }

  private stopPolling(): void {
    if (this.polling) window.clearTimeout(this.polling);
    this.polling = 0;
  }
}
