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
 */

import { el } from "./dom";
import { HoverTip } from "./hover-tip";
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

class ChipTip extends HoverTip {
  constructor(
    host: HTMLElement,
    private readonly groups: Map<string, Tag[]>,
    index: number,
  ) {
    super(host, `chips-tip-${index}`);
  }

  protected contents(): HTMLElement[] {
    const sections = Array.from(this.groups, ([category, chips]) =>
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
    return [
      el("span", {
        className: "chips-tip-head",
        text:
          `${text("context.tags")} chips a recordist can tap, one while it is happening. ` +
          `Faded ones have not come up yet. ${text("context.tags_witnessed")} have.`,
      }),
      ...sections,
    ];
  }
}
