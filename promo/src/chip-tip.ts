/**
 * The context vocabulary, on hover over the words that mention it.
 *
 * The page describes context chips in three places and never shows one, which
 * leaves "what a human saw" sounding like free text rather than a closed
 * vocabulary. This puts the actual list a hover away, without
 * spending a section of the page on it.
 *
 * The chips come from stats.json, so the tooltip is the vocabulary the phone is
 * serving rather than a copy of it somebody has to remember to update.
 *
 * Marked up as a plain element with `.chips` — the button is built here, so a
 * reader without JavaScript gets the word rather than a control that does
 * nothing. Hover is not the only way in: it opens on focus for a keyboard, and
 * on click for a touch screen that has no hover at all.
 */

import { el } from "./dom";
import { tags, text, type Tag } from "./stats";

/** Category keys are storage; these are what a reader should see. */
const CATEGORIES: Record<string, string> = {
  animals: "Animals",
  crows: "Crows",
  food: "Food",
  people: "People",
  quiet: "Quiet",
};

function grouped(all: Tag[]): Map<string, Tag[]> {
  const groups = new Map<string, Tag[]>();
  for (const tag of all) {
    const bucket = groups.get(tag.category) ?? [];
    bucket.push(tag);
    groups.set(tag.category, bucket);
  }
  return groups;
}

export class ChipTips {
  constructor(private readonly selector: string) {}

  mount(): void {
    const vocabulary = tags();
    if (!vocabulary.length) return;
    const groups = grouped(vocabulary);
    document
      .querySelectorAll<HTMLElement>(this.selector)
      .forEach((host, index) => new ChipTip(host, groups, index).mount());
  }
}

class ChipTip {
  private readonly id: string;
  private readonly button: HTMLButtonElement;
  private readonly tip: HTMLElement;
  private open = false;

  constructor(
    private readonly host: HTMLElement,
    groups: Map<string, Tag[]>,
    index: number,
  ) {
    this.id = `chips-tip-${index}`;
    this.button = el("button", {
      className: "chips-term",
      text: host.textContent?.trim() ?? "context",
      attrs: { type: "button", "aria-describedby": this.id, "aria-expanded": "false" },
    });
    this.tip = this.panel(groups);
  }

  mount(): void {
    this.host.replaceChildren(this.button, this.tip);

    this.button.addEventListener("pointerenter", () => this.show());
    this.button.addEventListener("focus", () => this.show());
    this.button.addEventListener("blur", () => this.hide());
    this.host.addEventListener("pointerleave", () => this.hide());

    // A touch screen never fires pointerenter on its own, and the click that
    // follows a tap would otherwise close what the tap just opened.
    this.button.addEventListener("click", (event) => {
      event.preventDefault();
      this.open ? this.hide() : this.show();
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") this.hide();
    });
    // The panel is fixed to the viewport (its ancestors clip absolute
    // children), so a scroll moves the word out from under it.
    window.addEventListener("scroll", () => this.open && this.place(), { passive: true });
    window.addEventListener("resize", () => this.open && this.place());
    document.addEventListener("pointerdown", (event) => {
      if (this.open && !this.host.contains(event.target as Node)) this.hide();
    });
  }

  private panel(groups: Map<string, Tag[]>): HTMLElement {
    const sections = Array.from(groups, ([category, chips]) =>
      el(
        "span",
        { className: "chips-group" },
        el("span", { className: "chips-group-name", text: CATEGORIES[category] ?? category }),
        el(
          "span",
          { className: "chips-list" },
          ...chips.map((chip) =>
            el("span", {
              className: "chips-chip",
              text: chip.label,
              // Faded rather than hidden. This is the vocabulary the phone
              // offers, not a list of things that happened, and a reader who
              // cannot tell the two apart will read "squirrel" as a sighting.
              attrs: chip.used ? {} : { "data-unused": "" },
            }),
          ),
        ),
      ),
    );
    return el(
      "span",
      { className: "chips-tip", attrs: { id: this.id, role: "tooltip" } },
      el("span", {
        className: "chips-tip-head",
        text:
          `${text("context.tags")} chips a recordist can tap, one while it is happening. ` +
          `Faded ones have not come up yet. ${text("context.tags_witnessed")} have.`,
      }),
      ...sections,
    );
  }

  private show(): void {
    this.open = true;
    this.host.dataset.open = "true";
    this.button.setAttribute("aria-expanded", "true");
    this.place();
  }

  private hide(): void {
    this.open = false;
    delete this.host.dataset.open;
    this.button.setAttribute("aria-expanded", "false");
  }

  /**
   * Anchor the panel to the word and nudge it back inside the viewport.
   *
   * The panel is position: fixed — an absolute child would be cut in half by
   * the overflow: hidden on the .pieces card grid — so the word's viewport
   * rect is the anchor. It is centred on a word that can sit anywhere in a
   * paragraph, so on a phone a centred panel runs off one edge or the other
   * most of the time, and the chips stack tall enough to clip off the top.
   * CSS cannot see either overflow; this measures once the panel is visible,
   * flips it below the word if it does not fit above, and shifts it sideways
   * by however much it is out by.
   */
  private place(): void {
    const margin = 12;
    const gap = 8;
    this.tip.style.removeProperty("--shift");
    this.tip.style.removeProperty("--max-height");
    delete this.host.dataset.below;

    // Whichever side has room. Capping at a fraction of the viewport is not
    // enough on its own — the word can sit near the bottom of the screen, and a
    // panel that fits the viewport still runs off the edge from there.
    const word = this.host.getBoundingClientRect();
    this.tip.style.setProperty("--anchor-x", `${Math.round(word.left + word.width / 2)}px`);
    this.tip.style.setProperty("--anchor-top", `${Math.round(word.bottom + gap)}px`);
    this.tip.style.setProperty(
      "--anchor-bottom",
      `${Math.round(window.innerHeight - word.top + gap)}px`,
    );
    const above = word.top - margin - gap;
    const below = window.innerHeight - word.bottom - margin - gap;
    const wanted = this.tip.scrollHeight;
    const goBelow = wanted > above && below > above;
    if (goBelow) this.host.dataset.below = "true";
    const room = goBelow ? below : above;
    if (wanted > room) this.tip.style.setProperty("--max-height", `${Math.round(room)}px`);

    // Re-measured: flipping moves the panel, so the sideways clamp has to run
    // against where it actually ended up.
    const box = this.tip.getBoundingClientRect();
    let shift = 0;
    if (box.left < margin) shift = margin - box.left;
    else if (box.right > window.innerWidth - margin) shift = window.innerWidth - margin - box.right;
    if (shift) this.tip.style.setProperty("--shift", `${Math.round(shift)}px`);
  }
}
