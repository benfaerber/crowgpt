/** Ask CrowGPT yourself: the one thing on the page that talks to a server.
 *
 * The field server keeps a shelf of clips generated ahead, so a press usually
 * plays at once; when the shelf for an item is bare the press becomes a live
 * job and this polls until the bout is done. No token rides along — the API
 * bounds presses per address and the menu is fixed server-side (the page only
 * names a key). Everything here is hidden until the API has answered health
 * and the menu, so a page whose server is down reads whole with the buttons
 * gone rather than spinning.
 */

import { Player } from "./caw-player";
import { el } from "./dom";

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
    try {
      const health = await fetch(`${this.api}/api/health`);
      if (!health.ok) return;
      const menu = await fetch(`${this.api}/api/demo/menu`);
      if (!menu.ok) return;
      items = ((await menu.json()) as { items: MenuItem[] }).items;
    } catch {
      return;
    }
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
  }

  private async press(item: MenuItem, button: HTMLButtonElement): Promise<void> {
    this.stopPolling();
    this.setBusy(button);
    this.say("Asking…");
    let generation: Generation;
    try {
      const response = await fetch(`${this.api}/api/demo/generate/${item.key}`, {
        method: "POST",
      });
      if (response.status === 429) {
        this.say("That is plenty of caws for one hour from one address. Come back later.");
        this.setBusy(null);
        return;
      }
      if (response.status === 503) {
        this.say("CrowGPT is busy answering other people. Try again in a minute.");
        this.setBusy(null);
        return;
      }
      if (!response.ok) throw new Error(`${response.status}`);
      generation = (await response.json()) as Generation;
    } catch {
      this.say("Could not reach CrowGPT just now.");
      this.setBusy(null);
      return;
    }
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
      const response = await fetch(`${this.api}/api/demo/generations/${id}`);
      if (!response.ok) throw new Error(`${response.status}`);
      this.follow(item, (await response.json()) as Generation);
    } catch {
      this.say("Lost touch with CrowGPT while it was generating. Try another press.");
      this.setBusy(null);
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
    for (const button of this.buttons) {
      button.disabled = active !== null;
      button.classList.toggle("is-asking", button === active);
    }
  }

  private stopPolling(): void {
    if (this.polling) window.clearTimeout(this.polling);
    this.polling = 0;
  }
}
