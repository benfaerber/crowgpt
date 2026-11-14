/** A generated clip as a chat voice note: play button, waveform, clock.
 *
 * The waveform is the clip's own, decoded in the browser from the one download
 * that also feeds the audio element. When decoding is not possible (an old
 * browser, a clip that will not parse) the bars fall back to a shape drawn
 * from the seed, so the bubble still looks like a voice note and still plays.
 */

import { el } from "./dom";

const BARS = 44;
const VOLUME = 0.45;

export class VoiceNote {
  readonly root: HTMLElement;
  private readonly audio = el("audio", { attrs: { preload: "auto" } });
  private readonly button = el("button", {
    className: "voice-play",
    attrs: { type: "button", "aria-label": "Play" },
  });
  private readonly wave = el("div", { className: "voice-wave", attrs: { role: "slider", "aria-label": "Seek" } });
  private readonly clock = el("span", { className: "voice-clock", text: "0:00" });
  private bars: HTMLElement[] = [];

  constructor(
    private readonly url: string,
    private readonly seed: number,
    private readonly onSpeaking: (speaking: boolean) => void,
  ) {
    this.audio.volume = VOLUME;
    this.root = el("div", { className: "voice-note" }, this.button, this.wave, this.clock, this.audio);
    this.button.addEventListener("click", () => this.toggle());
    this.wave.addEventListener("click", (event) => this.seek(event));
    for (const name of ["play", "pause", "ended", "timeupdate", "loadedmetadata"]) {
      this.audio.addEventListener(name, () => this.render());
    }
  }

  async load(): Promise<void> {
    try {
      const response = await fetch(this.url, { signal: AbortSignal.timeout(15000) });
      if (!response.ok) throw new Error(`${response.status}`);
      const bytes = await response.arrayBuffer();
      this.audio.src = URL.createObjectURL(new Blob([bytes], { type: response.headers.get("Content-Type") ?? "audio/wav" }));
      this.draw(await VoiceNote.peaks(bytes));
    } catch {
      this.audio.src = this.url;
      this.draw(this.seededPeaks());
    }
  }

  play(): void {
    void this.audio.play().catch(() => undefined);
  }

  stop(): void {
    this.audio.pause();
  }

  get playing(): boolean {
    return !this.audio.paused && !this.audio.ended;
  }

  onPlay(listener: () => void): void {
    this.audio.addEventListener("play", listener);
  }

  private toggle(): void {
    if (this.audio.paused) this.play();
    else this.audio.pause();
  }

  private seek(event: MouseEvent): void {
    if (!this.audio.duration) return;
    const box = this.wave.getBoundingClientRect();
    const fraction = Math.min(1, Math.max(0, (event.clientX - box.left) / box.width));
    this.audio.currentTime = fraction * this.audio.duration;
  }

  private draw(peaks: number[]): void {
    this.bars = peaks.map((peak) => {
      const bar = el("span", { className: "voice-bar" });
      bar.style.setProperty("--h", `${Math.max(10, Math.round(peak * 100))}%`);
      return bar;
    });
    this.wave.replaceChildren(...this.bars);
    this.render();
  }

  private render(): void {
    const playing = this.playing;
    const progress = this.audio.duration ? this.audio.currentTime / this.audio.duration : 0;
    const lit = Math.round(progress * this.bars.length);
    this.bars.forEach((bar, index) => bar.classList.toggle("is-played", index < lit));
    this.button.classList.toggle("is-playing", playing);
    this.button.setAttribute("aria-label", playing ? "Pause" : "Play");
    this.wave.setAttribute("aria-valuenow", (progress * 100).toFixed(0));
    const shown = Math.floor(playing || progress > 0 ? this.audio.currentTime : this.audio.duration || 0);
    this.clock.textContent = `0:${String(shown).padStart(2, "0")}`;
    this.onSpeaking(playing);
  }

  private static async peaks(bytes: ArrayBuffer): Promise<number[]> {
    const context = new OfflineAudioContext(1, 1, 22050);
    const buffer = await context.decodeAudioData(bytes.slice(0));
    const samples = buffer.getChannelData(0);
    const step = Math.max(1, Math.floor(samples.length / BARS));
    const peaks: number[] = [];
    for (let bar = 0; bar < BARS; bar++) {
      let sum = 0;
      for (let i = bar * step; i < Math.min(samples.length, (bar + 1) * step); i++) sum += samples[i] * samples[i];
      peaks.push(Math.sqrt(sum / step));
    }
    const loudest = Math.max(...peaks, 1e-6);
    return peaks.map((peak) => Math.sqrt(peak / loudest));
  }

  private seededPeaks(): number[] {
    let state = this.seed || 1;
    return Array.from({ length: BARS }, () => {
      state = (state * 1103515245 + 12345) & 0x7fffffff;
      return 0.25 + (state / 0x7fffffff) * 0.75;
    });
  }
}
