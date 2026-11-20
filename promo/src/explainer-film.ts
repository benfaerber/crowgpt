/**
 * The explainer film, as a poster that becomes the YouTube player on a click.
 *
 * The player is not loaded until someone asks for it: an embed costs every
 * visitor YouTube's scripts whether or not they press play. Without JavaScript
 * the poster stays what it is in the markup, a link to the video.
 */

import { el } from "./dom";

export class ExplainerFilm {
  constructor(private readonly selector: string) {}

  mount(): void {
    for (const poster of document.querySelectorAll<HTMLAnchorElement>(this.selector)) {
      const id = poster.dataset.video;
      if (!id) continue;
      poster.addEventListener("click", (event) => {
        event.preventDefault();
        poster.replaceWith(this.player(id, poster.getAttribute("aria-label") ?? ""));
      });
    }
  }

  private player(id: string, title: string): HTMLElement {
    return el("iframe", {
      className: "film-player",
      attrs: {
        src: `https://www.youtube-nocookie.com/embed/${id}?autoplay=1&rel=0`,
        title,
        allow: "autoplay; encrypted-media; picture-in-picture; fullscreen",
        allowfullscreen: "",
      },
    });
  }
}
