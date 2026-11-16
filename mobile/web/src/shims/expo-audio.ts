import { useEffect, useMemo, useState } from "react";

/**
 * The part of expo-audio the labelling desk plays through, over one
 * HTMLAudioElement.
 *
 * The desk asks very little of a player: load a recording, seek, play, pause,
 * and say where it is often enough to stop at the end of a call. A browser's
 * `timeupdate` arrives about four times a second, which overshoots a
 * half-second caw, so position is read every frame while something is playing.
 */
export interface AudioSource {
  uri: string;
}

type Listener = () => void;

let staged: HTMLMediaElement | undefined;

/**
 * Hand the next player an element to play through, in place of one of its own.
 *
 * How a video scan shows its picture without the desk knowing: the page puts
 * a <video> on screen and stages it here, and the desk's one player, asked
 * only for sound, plays, seeks and stops that element like any other.
 */
export function stageMediaElement(element: HTMLMediaElement | undefined): void {
  staged = element;
}

export class WebAudioPlayer {
  private readonly element: HTMLMediaElement = WebAudioPlayer.take();

  private static take(): HTMLMediaElement {
    const element = staged ?? new Audio();
    staged = undefined;
    return element;
  }

  private readonly listeners = new Set<Listener>();
  private frame: number | undefined;

  constructor() {
    this.element.preload = "auto";
    for (const event of ["play", "pause", "ended", "seeked", "loadedmetadata"]) {
      this.element.addEventListener(event, this.changed);
    }
  }

  get currentTime(): number {
    return this.element.currentTime;
  }

  get playing(): boolean {
    return !this.element.paused && !this.element.ended;
  }

  replace(source: AudioSource | null): void {
    const uri = source?.uri ?? "";
    if (this.element.getAttribute("src") === uri) return;
    this.element.pause();
    if (uri) this.element.src = uri;
    else this.element.removeAttribute("src");
  }

  play(): void {
    void this.element.play().catch(() => this.changed());
  }

  pause(): void {
    this.element.pause();
  }

  async seekTo(seconds: number): Promise<void> {
    this.element.currentTime = seconds;
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  release(): void {
    this.pause();
    if (this.frame !== undefined) cancelAnimationFrame(this.frame);
    for (const event of ["play", "pause", "ended", "seeked", "loadedmetadata"]) {
      this.element.removeEventListener(event, this.changed);
    }
    this.listeners.clear();
  }

  private readonly changed = () => {
    for (const listener of this.listeners) listener();
    if (this.playing && this.frame === undefined) this.frame = requestAnimationFrame(this.tick);
  };

  private readonly tick = () => {
    this.frame = undefined;
    this.changed();
  };
}

export function useAudioPlayer(source: AudioSource | null): WebAudioPlayer {
  const player = useMemo(() => new WebAudioPlayer(), []);
  const uri = source?.uri;
  useEffect(() => {
    player.replace(uri ? { uri } : null);
  }, [player, uri]);
  useEffect(() => () => player.release(), [player]);
  return player;
}

export function useAudioPlayerStatus(player: WebAudioPlayer): { playing: boolean; currentTime: number } {
  const [status, setStatus] = useState({ playing: player.playing, currentTime: player.currentTime });
  useEffect(
    () =>
      player.subscribe(() =>
        setStatus((before) =>
          before.playing === player.playing && before.currentTime === player.currentTime
            ? before
            : { playing: player.playing, currentTime: player.currentTime },
        ),
      ),
    [player],
  );
  return status;
}
