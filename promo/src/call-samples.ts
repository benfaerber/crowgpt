/**
 * A play button on each call-type card, so the five classes can be heard
 * rather than only described.
 *
 * The audio element in the card is the no-script fallback and the thing that
 * plays; this swaps the card's colour dot for a button in the same colour,
 * with the clip's progress drawn as a ring around it. One sample at a time:
 * starting a card stops whichever one was playing.
 */

import { el } from "./dom";

const VOLUME = 0.5;

export class CallSamples {
  private readonly samples: CallSample[] = [];

  constructor(private readonly selector: string) {}

  mount(): void {
    for (const card of document.querySelectorAll<HTMLElement>(this.selector)) {
      const audio = card.querySelector("audio");
      const name = card.querySelector<HTMLElement>(".call-name");
      if (!audio || !name) continue;
      const sample = new CallSample(card, name, audio, (playing) => this.solo(playing));
      sample.mount();
      this.samples.push(sample);
    }
  }

  private solo(playing: CallSample): void {
    for (const sample of this.samples) if (sample !== playing) sample.stop();
  }
}

class CallSample {
  private readonly button: HTMLButtonElement;

  constructor(
    private readonly card: HTMLElement,
    name: HTMLElement,
    private readonly audio: HTMLAudioElement,
    private readonly onPlay: (sample: CallSample) => void,
  ) {
    this.button = el("button", {
      className: "call-play",
      attrs: { type: "button", "aria-label": `Play ${name.textContent?.trim().toLowerCase()}` },
    });
    name.prepend(this.button);
  }

  mount(): void {
    this.audio.removeAttribute("controls");
    this.audio.volume = VOLUME;
    this.card.classList.add("has-sample");

    this.button.addEventListener("click", () => this.toggle());
    this.audio.addEventListener("play", () => this.render());
    this.audio.addEventListener("pause", () => this.render());
    this.audio.addEventListener("timeupdate", () => this.render());
    this.audio.addEventListener("ended", () => {
      this.audio.currentTime = 0;
      this.render();
    });
  }

  stop(): void {
    if (this.audio.paused) return;
    this.audio.pause();
    this.audio.currentTime = 0;
  }

  private toggle(): void {
    if (this.audio.paused) {
      this.onPlay(this);
      void this.audio.play();
    } else {
      this.audio.pause();
    }
  }

  private render(): void {
    const playing = !this.audio.paused && !this.audio.ended;
    const progress = this.audio.duration ? this.audio.currentTime / this.audio.duration : 0;
    this.button.style.setProperty("--progress", `${(progress * 100).toFixed(1)}%`);
    this.button.classList.toggle("is-playing", playing);
    this.button.setAttribute("aria-pressed", String(playing));
  }
}
