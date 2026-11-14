/** A scanned photo: the visitor's own picture with the bird the classifier
 *  judged boxed on it, and the species ranked beside it. */

import { el } from "./dom";

interface SpeciesScore {
  slug: string;
  common_name: string;
  scientific_name: string;
  probability: number;
}

export interface PhotoResult {
  ranking: SpeciesScore[];
  bird_box: { left: number; top: number; right: number; bottom: number; birds: number } | null;
  used_location: boolean;
  latitude: number | null;
  longitude: number | null;
  location_source: "exif" | "given" | null;
  width: number;
  height: number;
}

/** How many species to list. The rest are near zero. */
const SHOWN = 4;

function percent(probability: number): string {
  const value = probability * 100;
  if (value >= 99.5) return ">99%";
  return value < 1 ? "<1%" : `${Math.round(value)}%`;
}

export class ScanPhoto {
  constructor(
    private readonly result: PhotoResult,
    private readonly imageUrl: string,
    private readonly name: string,
  ) {}

  render(): HTMLElement {
    const best = this.result.ranking[0];
    const answer = el("div", { className: "scan-answer" },
      el("h3", { text: best.common_name }),
      el("p", { className: "scan-scientific", text: best.scientific_name }),
      this.ranking(),
    );
    for (const note of this.notes()) answer.append(el("p", { className: "scan-note", text: note }));
    return el("div", { className: "scan-photo" }, this.frame(), answer);
  }

  private frame(): HTMLElement {
    const frame = el("div", { className: "scan-frame" },
      el("img", { attrs: { src: this.imageUrl, alt: this.name } }));
    const box = this.result.bird_box;
    if (box) {
      const outline = el("div", {
        className: "scan-box",
        attrs: { title: "The bird the classifier judged" },
      });
      outline.style.left = `${(box.left / this.result.width) * 100}%`;
      outline.style.top = `${(box.top / this.result.height) * 100}%`;
      outline.style.width = `${((box.right - box.left) / this.result.width) * 100}%`;
      outline.style.height = `${((box.bottom - box.top) / this.result.height) * 100}%`;
      frame.append(outline);
    }
    return frame;
  }

  private ranking(): HTMLElement {
    const list = el("ul", { className: "scan-ranking" });
    for (const score of this.result.ranking.slice(0, SHOWN)) {
      const fill = el("span", { className: "scan-ranking-fill" });
      fill.style.width = `${score.probability * 100}%`;
      list.append(el("li", {},
        el("span", { className: "scan-ranking-name", text: score.common_name }),
        el("span", { className: "scan-ranking-track" }, fill),
        el("span", { className: "scan-ranking-value", text: percent(score.probability) }),
      ));
    }
    return list;
  }

  private notes(): string[] {
    const notes: string[] = [];
    if (this.result.bird_box === null) {
      notes.push("No bird was found, so this answer describes the whole photo. Treat it as a guess.");
    } else if (this.result.bird_box.birds > 1) {
      notes.push(`${this.result.bird_box.birds} birds were found; the largest was judged.`);
    }
    if (this.result.used_location && this.result.location_source === "exif") {
      notes.push("The photo's own GPS tags say where it was taken, and that was used to rule species in and out.");
    } else if (this.result.used_location) {
      notes.push(
        "Your approximate location was used to rule species in and out. If the photo " +
        "was taken somewhere else, untick the location box and scan it again.",
      );
    } else if (this.result.latitude !== null) {
      notes.push("The location was ignored: none of the nine species is recorded near there.");
    } else {
      notes.push(
        "No location came with the photo, so this is from the picture alone. Location is " +
        "what separates most look-alike crows.",
      );
    }
    notes.push("It knows nine corvids and always answers with one of them, even for a pigeon.");
    return notes;
  }
}
