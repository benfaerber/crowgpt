/** A loading bar that is a crow: it flies along a trail as the work goes, and
 * when the work is done it lands, turns into the cawing crow from the field
 * recording player, and caws twice to say so.
 *
 * The progress is an honest guess, not a measurement. With the server's
 * seconds-left estimate the crow sits at elapsed / (elapsed + left); without
 * one it creeps toward the far end and never quite arrives, so a slow job
 * reads as slow rather than stuck. Either way it stops short of the end until
 * `finish()`, because only the server knows when it is done.
 */

import { el } from "./dom";

const TICK_MS = 250;
const CEILING = 0.94;
const LANDING_MS = 650;
const CAW_MS = 1700;
const CAW_VOLUME = 0.35;
const CAW_URL = new URL("./assets/caws/done-caw.mp3", import.meta.url).href;

export class CrowLoader {
  readonly root: HTMLElement;
  private readonly trail = el("span", { className: "crow-loader-trail" });
  private readonly bird = el("span", { className: "crow-loader-bird" });
  private progress = 0;
  private started = 0;
  private secondsLeft: number | null = null;
  private timer = 0;

  constructor(private readonly announce = true) {
    this.root = el("div", {
      className: "crow-loader",
      attrs: { role: "progressbar", "aria-label": "Working", "aria-valuemin": "0", "aria-valuemax": "100" },
    }, this.trail, this.bird);
  }

  start(): void {
    this.stop();
    this.progress = 0;
    this.secondsLeft = null;
    this.started = performance.now();
    this.root.classList.remove("is-done", "is-landing");
    this.root.classList.add("is-flying");
    this.render();
    this.timer = window.setInterval(() => this.tick(), TICK_MS);
  }

  /** The server's latest guess at the seconds left; undefined when it has none. */
  estimate(secondsLeft: number | undefined): void {
    this.secondsLeft = secondsLeft ?? null;
  }

  /** Land and caw. Resolves once the caw has been seen, so the result can follow it. */
  async finish(): Promise<void> {
    window.clearInterval(this.timer);
    this.timer = 0;
    this.root.classList.add("is-landing");
    this.progress = 1;
    this.render();
    await new Promise((resolve) => window.setTimeout(resolve, LANDING_MS));
    this.root.classList.remove("is-flying", "is-landing");
    this.root.classList.add("is-done");
    if (this.announce) CrowLoader.caw();
    await new Promise((resolve) => window.setTimeout(resolve, CAW_MS));
  }

  stop(): void {
    window.clearInterval(this.timer);
    this.timer = 0;
    this.root.classList.remove("is-flying", "is-landing", "is-done");
  }

  private tick(): void {
    const elapsed = (performance.now() - this.started) / 1000;
    const target = this.secondsLeft !== null
      ? elapsed / (elapsed + Math.max(this.secondsLeft, 1))
      : this.progress + (CEILING - this.progress) * 0.015;
    this.progress = Math.min(CEILING, Math.max(this.progress, target));
    this.render();
  }

  private render(): void {
    this.root.style.setProperty("--progress", this.progress.toFixed(4));
    this.root.setAttribute("aria-valuenow", String(Math.round(this.progress * 100)));
  }

  private static caw(): void {
    const audio = new Audio(CAW_URL);
    audio.volume = CAW_VOLUME;
    void audio.play().catch(() => undefined);
  }
}
