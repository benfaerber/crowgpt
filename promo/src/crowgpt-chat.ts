/** The CrowGPT page: a chat where every reply is a freshly generated call.
 *
 * The visitor's side is a row of quick-reply chips, one per item the server's
 * menu offers; a press becomes their bubble, CrowGPT "types" while the clip is
 * fetched or generated, and the reply arrives as a voice note. The thread
 * lives only in this tab: the clips are the demo shelf's, not anybody's to keep.
 *
 * The server side is unchanged from when this was a row of buttons on the front
 * page: the field server keeps a shelf of clips generated ahead, so a press
 * usually answers at once; when the shelf is bare it becomes a live job and
 * this polls. Each press spends a single-use Turnstile token. The copy a field
 * server serves at /promo presses without one when that server neither has a
 * key nor requires one, which is what a local `make field` is; the public build
 * never does.
 */

import "./styles.css";

import { CawPlayers } from "./caw-player";
import { CrowLoader } from "./crow-loader";
import { DemoChallenge } from "./demo-challenge";
import { el } from "./dom";
import { VoiceNote } from "./voice-note";

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
}

class Refused extends Error {
  constructor(readonly status: number) {
    super(`${status}`);
  }
}

const POLL_MS = 3000;
const FRESH_SECONDS = 30;

const ASK: Record<string, string> = {
  "alarm call": "Sound the alarm! An alarm call, please.",
  call: "Just a normal call, please.",
  begging: "Can you beg like a fledgling?",
  song: "Sing me a song.",
};

const COLOUR: Record<string, string> = {
  "alarm call": "#f27070",
  call: "#6ea8fe",
  begging: "#efb057",
  song: "#c58af9",
};

class DemoApi {
  constructor(private readonly base: string) {}

  async menu(): Promise<{ items: MenuItem[]; turnstile_site_key?: string | null; turnstile_required?: boolean }> {
    const response = await this.fetch("/api/demo/menu");
    if (!response.ok) throw new Refused(response.status);
    return response.json();
  }

  async generate(key: string, token: string): Promise<Generation> {
    const response = await this.fetch(`/api/demo/generate/${key}`, {
      method: "POST",
      body: new URLSearchParams(token ? { "cf-turnstile-response": token } : {}),
    });
    if (!response.ok) throw new Refused(response.status);
    return response.json();
  }

  async generation(id: number): Promise<Generation> {
    const response = await this.fetch(`/api/demo/generations/${id}`);
    if (!response.ok) throw new Refused(response.status);
    return response.json();
  }

  clipUrl(generation: Generation): string {
    return `${this.base}${generation.clip}`;
  }

  private fetch(path: string, options?: RequestInit): Promise<Response> {
    return fetch(`${this.base}${path}`, { ...options, signal: AbortSignal.timeout(10000) });
  }
}

/** The perched crow in the header, and the little ones beside its bubbles. */
class Voice {
  private speakers = 0;

  constructor(private readonly avatar: HTMLElement, private readonly presence: HTMLElement) {}

  status(text: string): void {
    this.presence.textContent = text;
  }

  speaking(row: HTMLElement, speaking: boolean): void {
    if (row.classList.contains("is-speaking") === speaking) return;
    row.classList.toggle("is-speaking", speaking);
    this.speakers += speaking ? 1 : -1;
    this.avatar.classList.toggle("is-speaking", this.speakers > 0);
  }
}

class CrowChat {
  private readonly api = new DemoApi(__FIELD_API__);
  private readonly challenge = new DemoChallenge();
  private readonly chips: HTMLButtonElement[] = [];
  private readonly notes: VoiceNote[] = [];
  private readonly voice: Voice;
  private token = "";
  private verified = false;
  private busy = false;
  private offline = false;

  constructor(
    private readonly thread: HTMLElement,
    private readonly chipRow: HTMLElement,
    private readonly hint: HTMLElement,
    private readonly verify: HTMLElement,
    avatar: HTMLElement,
    presence: HTMLElement,
  ) {
    this.voice = new Voice(avatar, presence);
  }

  async mount(): Promise<void> {
    let items: MenuItem[];
    let siteKey: string | undefined;
    try {
      const menu = await this.api.menu();
      const unverifiedAllowed = __FIELD_API__ === "" && !menu.turnstile_required;
      if (!menu.turnstile_site_key && !unverifiedAllowed) return this.goOffline();
      items = menu.items;
      siteKey = menu.turnstile_site_key ?? undefined;
    } catch {
      return this.goOffline();
    }
    for (const item of items) this.chips.push(this.chip(item));
    this.chipRow.replaceChildren(...this.chips);
    this.verified = siteKey !== undefined;
    if (!siteKey) return this.refresh();
    this.refresh();
    try {
      await this.challenge.mount(this.verify, siteKey, (token) => {
        this.token = token;
        this.refresh();
      }, () => this.goOffline());
    } catch {
      this.goOffline();
    }
  }

  private chip(item: MenuItem): HTMLButtonElement {
    const chip = el("button", {
      className: "chat-chip",
      text: item.label,
      attrs: { type: "button", "data-key": item.key },
    });
    if (item.call_type && COLOUR[item.call_type]) chip.style.setProperty("--chip", COLOUR[item.call_type]);
    chip.addEventListener("click", () => void this.ask(item));
    return chip;
  }

  private ready(): boolean {
    return !this.offline && !this.busy && (!this.verified || this.token !== "");
  }

  private refresh(): void {
    for (const chip of this.chips) chip.disabled = !this.ready();
    if (this.offline) return;
    if (this.busy) this.hint.textContent = "CrowGPT is answering…";
    else if (this.verified && !this.token) this.hint.textContent = "One quick check that you're a human, not a crow…";
    else this.hint.textContent = "Ask for:";
    this.voice.status(this.busy ? "cawing…" : "perched · speaks fluent crow");
  }

  private async ask(item: MenuItem): Promise<void> {
    if (!this.ready()) return;
    const token = this.token;
    this.token = ""; // single-use, spent even when the request fails
    this.busy = true;
    this.refresh();
    this.mine(item.call_type ? ASK[item.call_type] ?? `${item.label}, please.` : `${item.label}, please.`);
    const typing = this.typing();
    try {
      let generation = await this.api.generate(item.key, token);
      let loader: CrowLoader | null = null;
      while (generation.state === "queued" || generation.state === "running") {
        if (!loader) loader = typing.load();
        typing.say(generation.ahead
          ? `generating… ${generation.ahead} ahead of you`
          : "generating a fresh one, about half a minute…");
        loader.estimate(generation.ahead ? undefined : FRESH_SECONDS);
        await new Promise((resolve) => window.setTimeout(resolve, POLL_MS));
        generation = await this.api.generation(generation.id);
      }
      if (loader && generation.state === "done") {
        typing.say("done!");
        await loader.finish();
      }
      typing.row.remove();
      if (generation.state === "failed") this.bot("That one came out garbled on the server. Ask me again?");
      else await this.reply(item, generation);
    } catch (error) {
      typing.row.remove();
      if (error instanceof Refused && error.status === 429) {
        this.bot("That's a lot of crow for one hour. Come back a little later and I'll caw again.");
      } else {
        this.goOffline();
      }
    } finally {
      this.busy = false;
      this.challenge.reset();
      this.refresh();
    }
  }

  private async reply(item: MenuItem, generation: Generation): Promise<void> {
    const row = this.botRow();
    const note = new VoiceNote(this.api.clipUrl(generation), generation.seed,
      (speaking) => this.voice.speaking(row, speaking));
    note.onPlay(() => this.notes.forEach((other) => other !== note && other.stop()));
    this.notes.push(note);
    const model = item.model === "crowgpt2" ? "CrowGPT2" : "CrowGPT";
    const what = item.call_type ?? "caw";
    const bubble = el("div", { className: "chat-bubble chat-bubble-bot chat-bubble-voice" },
      note.root,
      el("p", { className: "chat-meta", text: `${what} · generated by ${model} · seed ${generation.seed}` }));
    row.append(bubble);
    this.scroll();
    await note.load();
    note.play();
  }

  private mine(text: string): void {
    const row = el("li", { className: "chat-row chat-row-me" },
      el("div", { className: "chat-bubble chat-bubble-me", text }));
    this.thread.append(row);
    this.scroll();
  }

  private bot(text: string): void {
    const row = this.botRow();
    row.append(el("div", { className: "chat-bubble chat-bubble-bot", text }));
    this.scroll();
  }

  private botRow(): HTMLElement {
    const row = el("li", { className: "chat-row chat-row-bot" },
      el("span", { className: "chat-avatar", attrs: { "aria-hidden": "true" } }));
    this.thread.append(row);
    return row;
  }

  private typing(): { row: HTMLElement; say: (text: string) => void; load: () => CrowLoader } {
    const label = el("span", { className: "chat-typing-label", text: "cawing…" });
    const dots = el("span", { className: "chat-typing", attrs: { "aria-hidden": "true" } },
      el("span"), el("span"), el("span"));
    const bubble = el("div", { className: "chat-bubble chat-bubble-bot" }, dots, label);
    const row = this.botRow();
    row.append(bubble);
    this.scroll();
    return {
      row,
      say: (text) => { label.textContent = text; },
      load: () => {
        const loader = new CrowLoader();
        dots.remove();
        bubble.prepend(loader.root);
        loader.start();
        this.scroll();
        return loader;
      },
    };
  }

  private goOffline(): void {
    if (this.offline) return;
    this.offline = true;
    this.token = "";
    this.refresh();
    this.chipRow.replaceChildren();
    queueMicrotask(() => this.challenge.remove());
    this.voice.status("roosting · offline");
    this.hint.textContent = "";
    this.hint.append("The chat is offline right now. The examples ",
      el("a", { text: "below", attrs: { href: "#hear-it" } }), " still play.");
    this.bot("I'm off the wire right now: the server that runs me isn't answering. Try me again a little later.");
  }

  private scroll(): void {
    this.thread.scrollTo({ top: this.thread.scrollHeight, behavior: "smooth" });
  }
}

function need<T extends HTMLElement>(selector: string): T {
  const node = document.querySelector<T>(selector);
  if (!node) throw new Error(`crowgpt page is missing ${selector}`);
  return node;
}

new CawPlayers(".caw-player").mount();

void new CrowChat(
  need("#chat-thread"),
  need("#chat-chips"),
  need("#chat-hint"),
  need("#chat-verify"),
  need("#chat-avatar"),
  need("#chat-presence"),
).mount();
