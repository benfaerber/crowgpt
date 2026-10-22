/** The comparison players in the CrowGPT section: a crow flies across a sky.
 *
 * The native audio element stays in the markup as the no-script fallback and
 * as the thing that actually plays; this replaces its controls with a play
 * button and a strip of sky, and the playhead is a crow — parked on the left,
 * flying right as the clip plays, wings only beating while there is sound.
 * The sky is clickable to seek, because a progress bar that cannot seek reads
 * as broken the moment someone reaches for it.
 *
 * Opens quiet on purpose: an alarm call at full volume is a jump scare, not a
 * demo.
 */

import { el } from "./dom";

const DEFAULT_VOLUME = 0.45;

export class CawPlayers {
  private readonly figures: HTMLElement[];

  constructor(selector: string) {
    this.figures = Array.from(document.querySelectorAll(selector));
  }

  mount(): void {
    for (const figure of this.figures) {
      const audio = figure.querySelector("audio");
      if (audio) new Player(figure, audio).mount();
    }
  }
}

class Player {
  private readonly button = el("button", {
    className: "caw-play",
    attrs: { type: "button", "aria-label": "Play" },
  });
  private readonly crow = el("span", { className: "caw-sky-crow" });
  private readonly wave = el("span", { className: "caw-wave" });
  private readonly sky = el(
    "div",
    { className: "caw-sky", attrs: { role: "slider", "aria-label": "Seek" } },
    this.wave,
    this.crow,
  );
  private readonly clock = el("span", { className: "caw-clock", text: "0:00" });

  constructor(
    private readonly figure: HTMLElement,
    private readonly audio: HTMLAudioElement,
  ) {}

  mount(): void {
    // The native controls served no-script readers up to here; from now on
    // the custom ones are the interface and two sets would fight.
    this.audio.removeAttribute("controls");
    this.audio.volume = DEFAULT_VOLUME;
    this.figure.append(
      el("div", { className: "caw-deck" }, this.button, this.sky, this.clock),
    );

    this.button.addEventListener("click", () => this.toggle());
    this.sky.addEventListener("click", (event) => this.seek(event));
    this.audio.addEventListener("timeupdate", () => this.render());
    this.audio.addEventListener("loadedmetadata", () => this.render());
    this.audio.addEventListener("play", () => this.render());
    this.audio.addEventListener("pause", () => this.render());
    this.audio.addEventListener("ended", () => this.render());
    this.render();
  }

  private toggle(): void {
    if (this.audio.paused) {
      void this.audio.play();
    } else {
      this.audio.pause();
    }
  }

  private seek(event: MouseEvent): void {
    if (!this.audio.duration) return;
    const box = this.sky.getBoundingClientRect();
    const fraction = Math.min(1, Math.max(0, (event.clientX - box.left) / box.width));
    this.audio.currentTime = fraction * this.audio.duration;
  }

  private render(): void {
    const playing = !this.audio.paused && !this.audio.ended;
    const progress = this.audio.duration
      ? this.audio.currentTime / this.audio.duration
      : 0;
    // The crow stays put; the wave out of its beak is the playhead. Its run
    // starts past the bird and ends at the sky's right edge, so 100% of the
    // clip is 100% of the remaining air.
    this.wave.style.width = `calc(${(progress * 100).toFixed(2)}% - ${(progress * 40).toFixed(1)}px)`;
    this.crow.classList.toggle("is-flying", playing);
    this.wave.classList.toggle("is-flying", playing);
    this.button.classList.toggle("is-playing", playing);
    this.button.setAttribute("aria-label", playing ? "Pause" : "Play");
    this.sky.setAttribute("aria-valuenow", (progress * 100).toFixed(0));
    const shown = Math.floor(this.audio.currentTime);
    this.clock.textContent = `0:${String(shown).padStart(2, "0")}`;
  }
}
