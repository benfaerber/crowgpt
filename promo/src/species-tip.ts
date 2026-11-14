/**
 * The species count, with the species a hover away.
 *
 * "5 species" invites the question "which five?", and the answer is short
 * enough to sit in a tooltip rather than another line under the stat.
 */

import { el } from "./dom";
import { HoverTip } from "./hover-tip";
import { names } from "./stats";

export class SpeciesTip extends HoverTip {
  constructor(host: HTMLElement) {
    super(host, "species-tip");
  }

  protected contents(): HTMLElement[] {
    return [
      el("span", {
        className: "chips-tip-head",
        text: "One call-type model each:",
      }),
      el(
        "span",
        { className: "chips-list" },
        ...names("species.head_list").map((name) =>
          el("span", { className: "chips-chip", text: name }),
        ),
      ),
    ];
  }
}
