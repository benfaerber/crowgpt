/** On a phone the front page's dozen links fold behind one Menu button.
 *
 * Without the script the links show as they always did, wrapped; the button
 * only exists once this has run, and the CSS folds the links only when it has.
 */

import { el } from "./dom";

export class NavMenu {
  private readonly button = el("button", {
    className: "nav-toggle",
    attrs: { type: "button", "aria-expanded": "false" },
  }, el("span", { className: "nav-toggle-bars", attrs: { "aria-hidden": "true" } }), el("span", { text: "Menu" }));

  constructor(private readonly nav: HTMLElement, private readonly links: HTMLElement) {}

  static mountOn(selector: string): void {
    const nav = document.querySelector<HTMLElement>(selector);
    const links = nav?.querySelector<HTMLElement>(".nav-links");
    if (nav && links) new NavMenu(nav, links).mount();
  }

  mount(): void {
    if (!this.links.id) this.links.id = "nav-links";
    this.button.setAttribute("aria-controls", this.links.id);
    this.links.before(this.button);
    this.nav.classList.add("has-menu");
    this.button.addEventListener("click", () => this.toggle(!this.open));
    this.links.addEventListener("click", (event) => {
      if (event.target instanceof Element && event.target.closest("a")) this.toggle(false);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && this.open) {
        this.toggle(false);
        this.button.focus();
      }
    });
    document.addEventListener("click", (event) => {
      if (this.open && event.target instanceof Node && !this.nav.contains(event.target)) this.toggle(false);
    });
  }

  private get open(): boolean {
    return this.nav.classList.contains("is-open");
  }

  private toggle(open: boolean): void {
    this.nav.classList.toggle("is-open", open);
    this.button.setAttribute("aria-expanded", String(open));
  }
}
