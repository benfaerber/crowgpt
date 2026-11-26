/** A scanned photo: the visitor's own picture with the bird the classifier
 *  judged boxed on it, and the species ranked beside it. */

import { PhotoReading, percent, type PhotoResult } from "../../shared/scan";
import { el } from "./dom";

export type { PhotoResult };

export class ScanPhoto {
  private readonly reading: PhotoReading;

  constructor(
    private readonly result: PhotoResult,
    private readonly imageUrl: string,
    private readonly name: string,
  ) {
    this.reading = new PhotoReading(result);
  }

  render(): HTMLElement {
    const answer = el("div", { className: "scan-answer" }, ...this.headline());
    for (const note of this.notes()) answer.append(el("p", { className: "scan-note", text: note }));
    return el("div", { className: "scan-photo" }, this.frame(), answer);
  }

  private get verdict() {
    return this.reading.verdict;
  }

  /** A species is only the headline when a bird was found. A cat named as
   *  the crow it least unlike is the answer this page must not give. */
  private headline(): HTMLElement[] {
    const best = this.reading.best!;
    if (this.verdict === "other") {
      const subject = this.reading.instead;
      const article = /^[aeiou]/.test(subject) ? "an" : "a";
      return [
        el("h3", { text: "Not a corvid" }),
        el("p", { className: "scan-scientific", text: `This looks like a photo of ${article} ${subject}, and no bird was found in it.` }),
      ];
    }
    if (this.verdict === "no_bird") {
      return [
        el("h3", { text: "No bird found" }),
        el("p", { className: "scan-scientific", text: `If there is a corvid in this photo, the closest match is ${best.common_name}.` }),
        this.ranking(),
      ];
    }
    return [
      el("h3", { text: best.common_name }),
      el("p", { className: "scan-scientific", text: best.scientific_name }),
      this.ranking(),
    ];
  }

  private frame(): HTMLElement {
    const frame = el("div", { className: "scan-frame" },
      el("img", { attrs: { src: this.imageUrl, alt: this.name } }));
    const box = this.reading.box;
    if (box) {
      const outline = el("div", {
        className: "scan-box",
        attrs: { title: "The bird the classifier judged" },
      });
      Object.assign(outline.style, box);
      frame.append(outline);
    }
    return frame;
  }

  private ranking(): HTMLElement {
    const list = el("ul", { className: "scan-ranking" });
    for (const score of this.reading.top()) {
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
    if (this.verdict === "other") {
      return ["The scanner looks for a bird first, then tells nine corvids apart. If there is a crow in this photo, try one where it is larger in the frame."];
    }
    if (this.result.bird_box === null) {
      notes.push("The ranking describes the whole photo, so treat it as a guess. A photo where the bird is larger in the frame may do better.");
    } else if (this.reading.birds > 1) {
      notes.push(`${this.reading.birds} birds were found; the largest was judged.`);
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
    notes.push("It knows nine corvids. Another kind of bird, such as a pigeon or a hawk, is still answered with one of them.");
    return notes;
  }
}
