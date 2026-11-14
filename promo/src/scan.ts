/** The Scan page: a visitor's photo, recording or video, read by the project's
 *  server. A photo comes back as a species; sound comes back as a timeline.
 *
 *  The second thing on the site that talks to a server, after live-caw.ts, and
 *  bounded the same way: the server says which kinds it can read right now and
 *  whether an upload needs a Turnstile token. When it does not answer, the
 *  page says the scanner is offline and nothing else breaks.
 *
 *  The file is shown and played from the visitor's own device. What the server
 *  sends back is only the analysis.
 */

import "./styles.css";

import { DemoChallenge } from "./demo-challenge";
import { el } from "./dom";
import { ScanPhoto, type PhotoResult } from "./scan-photo";
import { ScanTimeline, type SoundResult } from "./scan-timeline";

type Kind = "photo" | "audio" | "video";

interface Config {
  kinds: Record<Kind, boolean>;
  formats: Record<Kind, string[]>;
  max_mb: Record<Kind, number>;
  sound_seconds: number;
  turnstile_site_key: string | null;
  turnstile_required: boolean;
}

interface Scan {
  id: string;
  kind: Kind;
  state: "queued" | "running" | "done" | "failed";
  ahead?: number;
  error?: string;
  result?: PhotoResult | SoundResult;
}

const POLL_MS = 1500;
const WAITING = {
  photo: "Looking at the photo…",
  audio: "Listening to the recording…",
  video: "Listening to the video's sound…",
};

class ScanApi {
  constructor(private readonly base: string) {}

  async config(): Promise<Config> {
    const response = await fetch(`${this.base}/api/demo/scan`, { signal: AbortSignal.timeout(10000) });
    if (!response.ok) throw new Error(`${response.status}`);
    return (await response.json()) as Config;
  }

  async upload(file: File, token: string, place: GeolocationCoordinates | null): Promise<Scan> {
    const form = new FormData();
    form.append("file", file);
    if (token) form.append("cf-turnstile-response", token);
    if (place) {
      form.append("latitude", String(place.latitude));
      form.append("longitude", String(place.longitude));
    }
    const response = await fetch(`${this.base}/api/demo/scan`, { method: "POST", body: form });
    if (!response.ok) throw new Error(await ScanApi.reason(response));
    return (await response.json()) as Scan;
  }

  async poll(id: string): Promise<Scan> {
    const response = await fetch(`${this.base}/api/demo/scan/${id}`, {
      signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) throw new Error(await ScanApi.reason(response));
    return (await response.json()) as Scan;
  }

  /** Flask answers refusals as a small HTML page; the sentence is in its <p>. */
  private static async reason(response: Response): Promise<string> {
    const body = await response.text();
    const sentence = /<p>([\s\S]*?)<\/p>/i.exec(body)?.[1]?.replace(/<[^>]+>/g, "").trim();
    if (sentence) return sentence.charAt(0).toUpperCase() + sentence.slice(1);
    return response.status === 413 ? "That file is too large." : "The scanner refused that file.";
  }
}

class ScanPage {
  private readonly api = new ScanApi(__FIELD_API__);
  private readonly challenge = new DemoChallenge("demo-scan");
  private config?: Config;
  private token = "";
  private busy = false;

  constructor(
    private readonly drop: HTMLElement,
    private readonly picker: HTMLInputElement,
    private readonly status: HTMLElement,
    private readonly results: HTMLElement,
    private readonly limits: HTMLElement,
    private readonly locate: HTMLInputElement,
    private readonly verification: HTMLElement,
  ) {}

  async mount(): Promise<void> {
    try {
      this.config = await this.api.config();
    } catch {
      this.say("The scanner is offline right now. Everything else on the site still works.");
      return;
    }
    // Only the copy a field server serves at /promo may upload unverified,
    // and only when that server asks for no verification: a local `make field`.
    if (!this.config.turnstile_site_key && (__FIELD_API__ !== "" || this.config.turnstile_required)) {
      this.say("Verification is unavailable, so the scanner is off for now.");
      return;
    }
    const offered = this.offered();
    if (offered.length === 0) {
      this.say("The scanner is resting right now. Try again in a little while.");
      return;
    }
    this.limits.textContent = this.describeLimits(offered);
    this.picker.accept = offered.flatMap(kind => this.config!.formats[kind].map(ext => `.${ext}`)).join(",");
    this.wire();
    if (this.config.turnstile_site_key) {
      try {
        await this.challenge.mount(this.verification, this.config.turnstile_site_key, token => {
          this.token = token;
          this.refresh();
        }, () => this.say("Verification is unavailable, so the scanner is off for now."));
      } catch {
        this.say("Verification is unavailable, so the scanner is off for now.");
        return;
      }
    }
    this.refresh();
  }

  private offered(): Kind[] {
    return (["photo", "audio", "video"] as Kind[]).filter(kind => this.config?.kinds[kind]);
  }

  private describeLimits(offered: Kind[]): string {
    const config = this.config!;
    const plural = { photo: "photos", audio: "audio", video: "video" };
    const parts = offered.map(kind => `${plural[kind]} up to ${config.max_mb[kind]} MB`);
    const sound = offered.some(kind => kind !== "photo")
      ? ` The first ${config.sound_seconds} seconds of a recording are scanned.`
      : "";
    const missing = (["photo", "audio", "video"] as Kind[]).filter(kind => !offered.includes(kind));
    const away = missing.length ? ` Not available right now: ${missing.join(", ")}.` : "";
    return `Reads ${parts.join(", ")}.${sound}${away}`;
  }

  private wire(): void {
    this.drop.addEventListener("click", () => { if (this.ready()) this.picker.click(); });
    this.drop.addEventListener("keydown", event => {
      if ((event.key === "Enter" || event.key === " ") && this.ready()) {
        event.preventDefault();
        this.picker.click();
      }
    });
    this.drop.addEventListener("dragover", event => {
      event.preventDefault();
      this.drop.classList.add("is-over");
    });
    this.drop.addEventListener("dragleave", () => this.drop.classList.remove("is-over"));
    this.drop.addEventListener("drop", event => {
      event.preventDefault();
      this.drop.classList.remove("is-over");
      const file = event.dataTransfer?.files[0];
      if (file) void this.scan(file);
    });
    this.picker.addEventListener("change", () => {
      const file = this.picker.files?.[0];
      this.picker.value = "";
      if (file) void this.scan(file);
    });
  }

  private ready(): boolean {
    const verified = !this.config?.turnstile_site_key || this.token !== "";
    return !this.busy && verified;
  }

  private refresh(): void {
    const waitingOnCheck = Boolean(this.config?.turnstile_site_key) && this.token === "";
    this.drop.classList.toggle("is-disabled", !this.ready());
    this.drop.setAttribute("aria-disabled", String(!this.ready()));
    if (!this.busy) this.say(waitingOnCheck ? "Checking you are not a robot…" : "");
  }

  private kindOf(file: File): Kind | null {
    const extension = file.name.includes(".") ? file.name.split(".").pop()!.toLowerCase() : "";
    return this.offered().find(kind => this.config!.formats[kind].includes(extension)) ?? null;
  }

  private async scan(file: File): Promise<void> {
    if (!this.ready() || !this.config) return;
    const kind = this.kindOf(file);
    if (!kind) {
      this.say(`This page cannot read ${file.name}. Try a JPEG or PNG photo, or an MP3, WAV, M4A or MP4.`);
      return;
    }
    if (file.size > this.config.max_mb[kind] * 1024 * 1024) {
      this.say(`${file.name} is over the ${this.config.max_mb[kind]} MB limit for ${kind} files.`);
      return;
    }
    this.busy = true;
    const token = this.token;
    this.token = ""; // single-use, spent whether or not the upload succeeds
    this.refresh();
    this.say("Uploading…");
    try {
      const place = this.locate.checked ? await this.whereAmI() : null;
      let scan = await this.api.upload(file, token, place);
      while (scan.state === "queued" || scan.state === "running") {
        this.say(scan.ahead ? `${scan.ahead} ahead of you in the queue…` : WAITING[kind]);
        await new Promise(resolve => window.setTimeout(resolve, POLL_MS));
        scan = await this.api.poll(scan.id);
      }
      if (scan.state === "failed" || !scan.result) {
        this.say(scan.error ?? "Could not read this file.");
      } else {
        this.show(file, kind, scan.result);
        this.say("");
      }
    } catch (error) {
      this.say(error instanceof Error && error.message.length > 3
        ? error.message
        : "The scanner did not answer. Try again in a minute.");
    } finally {
      this.busy = false;
      this.challenge.reset();
      this.refresh();
    }
  }

  private whereAmI(): Promise<GeolocationCoordinates | null> {
    return new Promise(resolve => {
      if (!navigator.geolocation) return resolve(null);
      navigator.geolocation.getCurrentPosition(
        position => resolve(position.coords),
        () => resolve(null),
        { timeout: 8000, maximumAge: 600000 },
      );
    });
  }

  private show(file: File, kind: Kind, result: PhotoResult | SoundResult): void {
    const url = URL.createObjectURL(file);
    const body = kind === "photo"
      ? new ScanPhoto(result as PhotoResult, url, file.name).render()
      : new ScanTimeline(result as SoundResult, this.player(kind, url)).render();
    const card = el("article", { className: "scan-result" },
      el("p", { className: "scan-file", text: file.name }), body);
    this.results.prepend(card);
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  private player(kind: Kind, url: string): HTMLMediaElement {
    const media = document.createElement(kind === "video" ? "video" : "audio");
    media.controls = true;
    media.preload = "metadata";
    media.src = url;
    media.className = "scan-media";
    if (kind === "video") (media as HTMLVideoElement).playsInline = true;
    return media;
  }

  private say(text: string): void {
    this.status.textContent = text;
    this.status.hidden = text === "";
  }
}

function need<T extends HTMLElement>(selector: string): T {
  const node = document.querySelector<T>(selector);
  if (!node) throw new Error(`scan page is missing ${selector}`);
  return node;
}

void new ScanPage(
  need("#scan-drop"),
  need<HTMLInputElement>("#scan-picker"),
  need("#scan-status"),
  need("#scan-results"),
  need("#scan-limits"),
  need<HTMLInputElement>("#scan-locate"),
  need("#scan-verification"),
).mount();
