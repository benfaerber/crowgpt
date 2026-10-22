/**
 * The contact address, kept out of the HTML a scraper reads.
 *
 * Harvesters overwhelmingly work on the raw markup — fetch the page, run a
 * regex for something@something, move on. So the address is not in the markup:
 * it is ROT13 in a data attribute, and the real `mailto:` link is assembled in
 * the DOM at runtime. That defeats the regex without costing a real visitor
 * anything, since anyone with a browser gets an ordinary clickable link.
 *
 * It is obfuscation, not encryption. Anything that runs the page's JavaScript
 * can still read the address; the point is that almost nothing harvesting at
 * scale bothers to.
 */

import { el } from "./dom";

/** Symmetric, so the same function encodes and decodes. */
function rot13(value: string): string {
  return value.replace(/[a-z]/gi, (ch) => {
    const base = ch <= "Z" ? 65 : 97;
    return String.fromCharCode(((ch.charCodeAt(0) - base + 13) % 26) + base);
  });
}

export class MailLink {
  constructor(private readonly selector: string) {}

  mount(): void {
    for (const holder of document.querySelectorAll<HTMLElement>(this.selector)) {
      // User and domain are held apart so the markup contains no @ at all —
      // ROT13 of the whole address is still email-shaped, and a harvester
      // regex would happily collect the scrambled version.
      const user = holder.dataset.u;
      const domain = holder.dataset.d;
      if (!user || !domain) continue;
      const address = `${rot13(user)}@${rot13(domain)}`;

      const link = el("a", {
        text: address,
        attrs: { href: `mailto:${address}`, rel: "nofollow" },
      });
      holder.replaceChildren(link);
    }
  }
}
