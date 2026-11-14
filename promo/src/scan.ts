/** The Scan page: a visitor's photo, recording or video, read by the project's
 *  server. A photo comes back as a species; sound comes back as a timeline.
 *
 *  The second thing on the site that talks to a server, after the CrowGPT chat, and
 *  bounded the same way: the server says which kinds it can read right now and
 *  whether an upload needs a Turnstile token. When it does not answer, the
 *  page says the scanner is offline and nothing else breaks.
 *
 *  The file is shown and played from the visitor's own device. What the server
 *  sends back is only the analysis.
 */

import "./styles.css";

import { CrowLoader } from "./crow-loader";
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
  eta_seconds?: number;
  kept?: boolean;
  error?: string;
  result?: PhotoResult | SoundResult;
}

/** Where the visitor roughly is, by their internet address. */
interface Place {
  latitude: number;
  longitude: number;
  label: string;
}

/** Finds the visitor's approximate location without asking the browser for
 *  it: the public site's own /geo, which is Cloudflare's estimate. The copy a
 *  field server serves has no /geo, so `?near=lat,lon` stands in there. */
class Whereabouts {
  constructor(private readonly url: string, private readonly allowOverride: boolean) {}

  async find(): Promise<Place | null> {
    return (this.allowOverride && this.fromQuery()) || this.fromNetwork();
  }

  private fromQuery(): Place | null {
    const near = new URLSearchParams(window.location.search).get("near");
    const [latitude, longitude] = (near ?? "").split(",").map(Number);
    if (!near || !Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;
    return { latitude, longitude, label: `${latitude.toFixed(2)}, ${longitude.toFixed(2)}` };
  }

  private async fromNetwork(): Promise<Place | null> {
    if (!this.url) return null;
    try {
      const response = await fetch(this.url, { signal: AbortSignal.timeout(5000) });
      if (!response.ok) return null;
      const body = (await response.json()) as {
        latitude: number | null; longitude: number | null;
        city: string | null; region: string | null; country: string | null;
      };
      if (body.latitude === null || body.longitude === null) return null;
      const names = [body.city, body.region ?? body.country].filter(Boolean);
      return {
        latitude: body.latitude,
        longitude: body.longitude,
        label: names.length ? `near ${names.join(", ")}` : "roughly where you are",
      };
    } catch {
      return null;
    }
  }
}

const POLL_MS = 1500;
const WAITING = {
  photo: "Looking at the photo…",
  audio: "Listening to the recording…",
  video: "Listening to the video's sound…",
};

/** The wait, counted down between polls. The server's guess replaces the
 *  local count on every poll; at zero it says so instead of going quiet,
 *  because a silent overdue wait reads as a broken page. The numbers are
 *  hidden from screen readers, which would otherwise announce every second. */
class Countdown {
  private seconds: number | null = null;
  private timer = 0;
  private readonly label = el("span");
  private readonly remaining = el("span", { className: "scan-eta" });

  constructor(private readonly host: HTMLElement) {
    this.remaining.setAttribute("aria-hidden", "true");
  }

  show(label: string, seconds: number | undefined): void {
    if (!this.label.isConnected) this.host.replaceChildren(this.label, this.remaining);
    this.host.hidden = false;
    this.label.textContent = label;
    this.seconds = seconds ?? null;
    this.render();
    if (!this.timer) this.timer = window.setInterval(() => this.tick(), 1000);
  }

  stop(): void {
    window.clearInterval(this.timer);
    this.timer = 0;
  }

  private tick(): void {
    if (this.seconds !== null && this.seconds > 0) this.seconds -= 1;
    this.render();
  }

  private render(): void {
    this.remaining.textContent = this.seconds === null ? "" : ` ${Countdown.phrase(this.seconds)}`;
  }

  static phrase(seconds: number): string {
    if (seconds <= 0) return "Taking longer than usual, still working.";
    if (seconds < 60) return `About ${seconds} second${seconds === 1 ? "" : "s"} left.`;
    const minutes = Math.ceil(seconds / 60);
    return `About ${minutes} minutes left.`;
  }
}

class ScanApi {
  constructor(private readonly base: string) {}

  async config(): Promise<Config> {
    const response = await fetch(`${this.base}/api/demo/scan`, { signal: AbortSignal.timeout(10000) });
    if (!response.ok) throw new Error(`${response.status}`);
    return (await response.json()) as Config;
  }

  async upload(file: File, token: string, place: Place | null, keep: boolean): Promise<Scan> {
    const form = new FormData();
    form.append("file", file);
    if (keep) form.append("keep", "1");
    if (place) {
      form.append("latitude", String(place.latitude));
      form.append("longitude", String(place.longitude));
    }
    // In a header, not the form: the server checks it before reading the file.
    const response = await fetch(`${this.base}/api/demo/scan`, {
      method: "POST",
      body: form,
      headers: token ? { "X-Turnstile-Token": token } : {},
    });
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
  private place: Place | null = null;
  private readonly countdown: Countdown;
  private readonly loader = new CrowLoader();
  private readonly whereabouts = new Whereabouts(__GEO_URL__, __FIELD_API__ === "");

  constructor(
    private readonly drop: HTMLElement,
    private readonly picker: HTMLInputElement,
    private readonly status: HTMLElement,
    private readonly results: HTMLElement,
    private readonly limits: HTMLElement,
    private readonly locate: HTMLInputElement,
    private readonly locateRow: HTMLElement,
    private readonly placeName: HTMLElement,
    private readonly verification: HTMLElement,
    private readonly keep: HTMLInputElement,
  ) {
    this.countdown = new Countdown(status);
    this.drop.querySelector(".scan-drop-sky")?.append(this.loader.root);
  }

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
    void this.locateVisitor();
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

  /** Not awaited by mount: a slow or absent lookup must not hold the page. */
  private async locateVisitor(): Promise<void> {
    this.place = await this.whereabouts.find();
    if (!this.place) return;
    this.placeName.textContent = this.place.label;
    this.locateRow.hidden = false;
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
    this.drop.dataset.state = "busy";
    this.drop.dataset.kind = kind;
    this.loader.start();
    const token = this.token;
    this.token = ""; // single-use, spent whether or not the upload succeeds
    this.refresh();
    this.say("Uploading…");
    try {
      const place = this.locate.checked ? this.place : null;
      const offered = this.keep.checked;
      this.keep.checked = false; // asked afresh for every file
      let scan = await this.api.upload(file, token, place, offered);
      while (scan.state === "queued" || scan.state === "running") {
        this.countdown.show(
          scan.ahead ? `${scan.ahead} ahead of you in the queue…` : WAITING[kind], scan.eta_seconds);
        this.loader.estimate(scan.eta_seconds);
        await new Promise(resolve => window.setTimeout(resolve, POLL_MS));
        scan = await this.api.poll(scan.id);
      }
      if (scan.state === "failed" || !scan.result) {
        this.say(scan.error ?? "Could not read this file.");
      } else {
        this.countdown.stop();
        await this.loader.finish();
        this.show(file, kind, scan.result, offered ? scan.kept === true : null);
        this.say("");
      }
    } catch (error) {
      this.say(error instanceof Error && error.message.length > 3
        ? error.message
        : "The scanner did not answer. Try again in a minute.");
    } finally {
      this.countdown.stop();
      this.loader.stop();
      this.busy = false;
      delete this.drop.dataset.state;
      this.challenge.reset();
      this.refresh();
    }
  }

  private show(file: File, kind: Kind, result: PhotoResult | SoundResult, kept: boolean | null): void {
    const url = URL.createObjectURL(file);
    const body = kind === "photo"
      ? new ScanPhoto(result as PhotoResult, url, file.name).render()
      : new ScanTimeline(result as SoundResult, this.player(kind, url)).render();
    const card = el("article", { className: "scan-result" },
      el("p", { className: "scan-file", text: file.name }), body);
    if (kept !== null) {
      card.append(el("p", { className: "scan-kept", text: kept
        ? "Kept for the project, as you asked. Thank you."
        : "Not kept: the project's space for contributed files is full. The file was deleted." }));
    }
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
    this.countdown.stop();
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
  need("#scan-locate-row"),
  need("#scan-place"),
  need("#scan-verification"),
  need<HTMLInputElement>("#scan-keep"),
).mount();
