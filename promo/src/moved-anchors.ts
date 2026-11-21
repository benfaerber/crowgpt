/** Sections that left the front page for pages of their own.
 *
 * Old links like crowgpt.org/#results were shared before the split; without
 * this they land at the top of the front page with nothing to say why. An
 * anchor that still exists here is left alone.
 */

const MOVED: Record<string, string> = {
  "two-problems": "./cawdex.html",
  results: "./cawdex.html",
  "auc-figure": "./cawdex.html",
  reading: "./crows.html",
  "photo-shredder": "./crows.html",
};

export class MovedAnchors {
  follow(): void {
    const id = decodeURIComponent(window.location.hash.slice(1));
    if (!id || document.getElementById(id) || !(id in MOVED)) return;
    window.location.replace(`${MOVED[id]}#${id}`);
  }
}
