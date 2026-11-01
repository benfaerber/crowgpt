/**
 * A `#` link on every heading, so any title on the page can be linked to.
 *
 * A section title takes its section's id, which is what the existing
 * `crowgpt.org/#cawscout` style links already point at. Every other heading is
 * slugged from its own text.
 *
 * The ids for subheads only exist once this has run, and the photos and the
 * AUC chart shift the layout after first paint, so the browser's own jump to
 * the hash is redone here once the page has settled.
 */

import { el } from "./dom";

export class HeadingAnchors {
  private readonly taken = new Set<string>();

  constructor(private readonly selector: string) {}

  mount(): void {
    for (const node of document.querySelectorAll<HTMLElement>("[id]")) {
      this.taken.add(node.id);
    }
    for (const heading of document.querySelectorAll<HTMLElement>(this.selector)) {
      const id = this.idFor(heading);
      if (!id) continue;
      heading.classList.add("anchored");
      heading.append(
        el("a", {
          className: "heading-anchor",
          text: "#",
          attrs: { href: `#${id}`, "aria-label": `Link to ${heading.textContent?.trim() ?? id}` },
        }),
      );
    }
    this.revisitHash();
  }

  private idFor(heading: HTMLElement): string | null {
    const section = heading.closest("section[id]");
    if (heading.tagName === "H2" && section && section.querySelector("h2") === heading) {
      return section.id;
    }
    if (heading.id) return heading.id;
    const base = HeadingAnchors.slug(heading.textContent ?? "");
    if (!base) return null;
    let id = base;
    for (let n = 2; this.taken.has(id); n++) id = `${base}-${n}`;
    this.taken.add(id);
    heading.id = id;
    return id;
  }

  private revisitHash(): void {
    const jump = () => {
      const id = decodeURIComponent(location.hash.slice(1));
      if (id) document.getElementById(id)?.scrollIntoView();
    };
    jump();
    if (document.readyState !== "complete") window.addEventListener("load", jump, { once: true });
  }

  private static slug(text: string): string {
    return text
      .toLowerCase()
      .normalize("NFKD")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
  }
}
