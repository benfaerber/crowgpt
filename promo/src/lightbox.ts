/**
 * Click a photo, get it full size, and move through everything on the page.
 *
 * The gallery is whatever is marked up as a figure carrying an image or a video
 * — the crows, the field kit, the phone screenshots, the light post — collected
 * in document order so the arrows walk the page the way a reader would.
 *
 * The inline video keeps its own controls and does not open the viewer when
 * clicked, because clicking a video means play. It is still a slide, so the
 * arrows reach it.
 */

import { el } from "./dom";

interface Slide {
  kind: "image" | "video";
  src: string;
  poster?: string;
  alt: string;
  caption: string;
}

export class Lightbox {
  private readonly slides: Slide[] = [];
  /** Which slide each figure became, so anything else on the page can open one. */
  private readonly positions = new Map<HTMLElement, number>();
  private index = 0;
  private root: HTMLDivElement | null = null;
  private image: HTMLImageElement | null = null;
  private video: HTMLVideoElement | null = null;
  private caption: HTMLParagraphElement | null = null;
  private counter: HTMLSpanElement | null = null;
  private lastFocused: Element | null = null;
  private pending: AbortController | null = null;

  constructor(private readonly selector: string) {}

  mount(): void {
    const figures = Array.from(document.querySelectorAll<HTMLElement>(this.selector));
    for (const figure of figures) {
      const caption = figure.querySelector("figcaption")?.textContent?.trim() ?? "";
      const media = figure.querySelector<HTMLVideoElement>("video");
      if (media) {
        const source = media.querySelector("source");
        this.positions.set(figure, this.slides.length);
        this.slides.push({
          kind: "video",
          src: source?.src ?? media.currentSrc ?? "",
          poster: media.poster,
          alt: "",
          caption,
        });
        continue;
      }

      const image = figure.querySelector("img");
      if (!image) continue;
      const position = this.slides.length;
      this.positions.set(figure, position);
      this.slides.push({
        kind: "image",
        src: image.currentSrc || image.src,
        alt: image.alt,
        caption,
      });
      // A photo that opens something is a control, so it answers to the keyboard
      // and says so, rather than being a div that happens to click.
      image.tabIndex = 0;
      image.setAttribute("role", "button");
      image.setAttribute("aria-label", `${image.alt || "Photo"}, open larger`);
      image.addEventListener("click", () => this.open(position));
      image.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          this.open(position);
        }
      });
    }
    if (this.slides.length) this.build();
  }

  /**
   * Open the slide a given figure became.
   *
   * For images the figure's own click already does this, but a video figure
   * deliberately has no such handler — clicking a video means play. This is the
   * way in for anything that wants to show one anyway, like a crow in the hero
   * pointing at the clip it is in.
   */
  openFigure(figure: HTMLElement): boolean {
    const position = this.positions.get(figure);
    if (position === undefined) return false;
    this.open(position);
    return true;
  }

  private build(): void {
    const button = (className: string, label: string, glyph: string) =>
      el("button", { className, text: glyph, attrs: { type: "button", "aria-label": label } });

    const close = button("lightbox-close", "Close", "×");
    const prev = button("lightbox-nav lightbox-prev", "Previous", "‹");
    const next = button("lightbox-nav lightbox-next", "Next", "›");

    const image = el("img", { attrs: { alt: "" } });
    const video = el("video", { attrs: { controls: "", playsinline: "", preload: "none" } });
    video.hidden = true;
    const caption = el("p", { className: "lightbox-caption" });
    const counter = el("span", { className: "lightbox-counter" });
    const stage = el(
      "figure",
      { className: "lightbox-stage" },
      image,
      video,
      el("figcaption", {}, caption, counter),
    );

    const root = el("div", {
      className: "lightbox",
      attrs: { role: "dialog", "aria-modal": "true", "aria-label": "Photo viewer" },
    });
    root.hidden = true;
    root.append(close, prev, next, stage);
    document.body.append(root);

    this.root = root;
    this.image = image;
    this.video = video;
    this.caption = caption;
    this.counter = counter;

    close.addEventListener("click", () => this.close());
    prev.addEventListener("click", () => this.step(-1));
    next.addEventListener("click", () => this.step(1));
    // Only the backdrop closes; a click that lands on the media or the arrows is
    // someone using the viewer, not dismissing it.
    root.addEventListener("click", (event) => {
      if (event.target === root) this.close();
    });
    document.addEventListener("keydown", (event) => {
      if (root.hidden) return;
      if (event.key === "Escape") this.close();
      if (event.key === "ArrowLeft") this.step(-1);
      if (event.key === "ArrowRight") this.step(1);
    });
  }

  private open(index: number): void {
    if (!this.root) return;
    this.lastFocused = document.activeElement;
    this.index = index;
    this.show();
    this.root.hidden = false;
    document.body.classList.add("lightbox-open");
    this.root.querySelector<HTMLButtonElement>(".lightbox-close")!.focus();
  }

  private close(): void {
    if (!this.root) return;
    this.video?.pause();
    this.root.hidden = true;
    document.body.classList.remove("lightbox-open");
    (this.lastFocused as HTMLElement | null)?.focus?.();
  }

  private step(delta: number): void {
    this.index = (this.index + delta + this.slides.length) % this.slides.length;
    this.show();
  }

  private show(): void {
    const slide = this.slides[this.index];
    if (!this.image || !this.video || !this.caption || !this.counter) return;

    // Whichever is not showing gets emptied as well as hidden — a video left
    // with a src keeps buffering behind a photo, and 5 MB is too much to spend
    // on something nobody is looking at.
    this.video.pause();
    const isVideo = slide.kind === "video";
    this.image.hidden = isVideo;
    this.video.hidden = !isVideo;

    if (isVideo) {
      this.image.removeAttribute("src");
      if (slide.poster) this.video.poster = slide.poster;
      if (this.video.getAttribute("src") !== slide.src) this.video.src = slide.src;
    } else {
      this.video.removeAttribute("src");
      this.video.load();
      this.showImage(slide);
    }

    this.caption.textContent = slide.caption;
    this.counter.textContent = `${this.index + 1} / ${this.slides.length}`;
  }

  /**
   * Swap the picture without showing the previous one first.
   *
   * Setting `src` does not blank an <img> — the browser keeps painting the old
   * bitmap until the new one has decoded. Opening the viewer a second time
   * therefore flashes whatever was in it last, which is most obvious coming
   * from a crow in the hero, where the photo is usually far down the page and
   * not loaded yet.
   */
  private showImage(slide: Slide): void {
    const image = this.image;
    if (!image) return;
    if (image.getAttribute("src") === slide.src) {
      image.classList.remove("is-loading");
      return;
    }

    image.classList.add("is-loading");
    image.src = slide.src;
    image.alt = slide.alt;

    // `complete` is already true when the picture came from cache, and no load
    // event follows — waiting for one would leave it hidden for good.
    const reveal = () => image.classList.remove("is-loading");
    if (image.complete) {
      reveal();
      return;
    }

    // One controller for both events and for the previous slide's pair: `once`
    // only removes the listener that actually fired, so stepping through a
    // gallery would otherwise leave a dead handler behind on every slide.
    this.pending?.abort();
    this.pending = new AbortController();
    const { signal } = this.pending;
    image.addEventListener("load", reveal, { signal });
    image.addEventListener("error", reveal, { signal });
  }
}
