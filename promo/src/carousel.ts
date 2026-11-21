/** A row of figures that scrolls sideways: swiped on a phone, where the next
 * one peeking in at the edge says there is more, and stepped with arrows
 * where there is a pointer. The scrolling is the browser's own (scroll snap),
 * so without this script the row still swipes; it only adds the arrows.
 */

import { el } from "./dom";

export class Carousel {
  private readonly prev = Carousel.arrow("carousel-prev", "Previous", "‹");
  private readonly next = Carousel.arrow("carousel-next", "Next", "›");

  constructor(private readonly root: HTMLElement, private readonly track: HTMLElement) {}

  static mountAll(selector: string): void {
    for (const root of document.querySelectorAll<HTMLElement>(selector)) {
      const track = root.querySelector<HTMLElement>(".carousel-track");
      if (track) new Carousel(root, track).mount();
    }
  }

  mount(): void {
    this.root.append(this.prev, this.next);
    this.prev.addEventListener("click", () => this.step(-1));
    this.next.addEventListener("click", () => this.step(1));
    this.track.addEventListener("scroll", () => this.refresh(), { passive: true });
    new ResizeObserver(() => this.refresh()).observe(this.track);
    this.refresh();
  }

  private step(direction: 1 | -1): void {
    const item = this.track.firstElementChild as HTMLElement | null;
    const gap = parseFloat(getComputedStyle(this.track).columnGap) || 0;
    const width = (item?.offsetWidth ?? this.track.clientWidth) + gap;
    const perView = Math.max(1, Math.floor((this.track.clientWidth + gap) / width));
    const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.track.scrollBy({ left: direction * width * perView, behavior: smooth ? "smooth" : "auto" });
  }

  private refresh(): void {
    const end = this.track.scrollWidth - this.track.clientWidth;
    this.prev.disabled = this.track.scrollLeft <= 2;
    this.next.disabled = this.track.scrollLeft >= end - 2;
    this.root.classList.toggle("is-scrollable", end > 2);
  }

  private static arrow(className: string, label: string, glyph: string): HTMLButtonElement {
    return el("button", {
      className: `carousel-arrow ${className}`,
      text: glyph,
      attrs: { type: "button", "aria-label": label },
    });
  }
}
