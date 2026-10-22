/**
 * The attribution roll: every Xeno-canto recording the models learned from.
 *
 * The data is fetched rather than bundled — it is bigger than the rest of the
 * site put together, and nobody reaching the front page should pay for it.
 *
 * Ten thousand links is enough DOM to stall a phone if built in one go, so the
 * roll renders in chunks between frames. The filter re-renders the same way,
 * which keeps typing responsive on a list this size.
 */

import "./styles.css";

import { el } from "./dom";

interface Recordist {
  name: string;
  ids: string[];
}

interface Credits {
  source: string;
  url: string;
  counts: { recordings: number; recordists: number; species: number };
  licences: [string, number][];
  recordists: Recordist[];
}

const CHUNK = 40;

class CreditsPage {
  private data: Credits | null = null;
  private pending = 0;

  private readonly roll = document.querySelector<HTMLElement>("#credits-roll");
  private readonly summary = document.querySelector<HTMLElement>("#credits-summary");
  private readonly count = document.querySelector<HTMLElement>("#credits-count");
  private readonly filter = document.querySelector<HTMLInputElement>("#credits-filter");

  async load(): Promise<void> {
    // Relative, so the same build works at / on the public host and at /promo
    // on the field server.
    const response = await fetch("./credits.json");
    this.data = (await response.json()) as Credits;
    this.renderSummary();
    this.show(this.data.recordists);

    this.filter?.addEventListener("input", () => this.apply());
  }

  private renderSummary(): void {
    if (!this.summary || !this.data) return;
    const { recordings, recordists, species } = this.data.counts;
    const stat = (label: string, value: string, note: string) =>
      el(
        "div",
        { className: "stat" },
        el("dt", { text: label }),
        el("dd", { className: "stat-value", text: value }),
        el("p", { className: "stat-note", text: note }),
      );
    const top = this.data.licences
      .slice(0, 3)
      .map(([name, n]) => `${name} (${n.toLocaleString()})`)
      .join(", ");
    this.summary.replaceChildren(
      stat("Recordings learned from", recordings.toLocaleString(), "Every one on this page"),
      stat("Recordists", recordists.toLocaleString(), "People who made and shared them"),
      stat("Corvid species", String(species), "Across the whole archive pull"),
      stat("Licences", String(this.data.licences.length), top),
    );
  }

  private apply(): void {
    if (!this.data) return;
    const term = (this.filter?.value ?? "").trim().toLowerCase();
    if (!term) {
      this.show(this.data.recordists);
      return;
    }
    // An ID search should show only the matching recording, not the thousand
    // others by the same person.
    const matches: Recordist[] = [];
    for (const person of this.data.recordists) {
      if (person.name.toLowerCase().includes(term)) {
        matches.push(person);
      } else {
        const ids = person.ids.filter((id) => id.includes(term));
        if (ids.length) matches.push({ name: person.name, ids });
      }
    }
    this.show(matches);
  }

  private show(people: Recordist[]): void {
    if (!this.roll || !this.count) return;
    this.pending += 1;
    const run = this.pending;

    const recordings = people.reduce((sum, p) => sum + p.ids.length, 0);
    this.count.textContent = people.length
      ? `${recordings.toLocaleString()} recording${recordings === 1 ? "" : "s"} by ${people.length.toLocaleString()} recordist${people.length === 1 ? "" : "s"}`
      : "Nothing matches that.";

    this.roll.replaceChildren();
    let index = 0;
    const step = () => {
      // A newer render started; abandon this one rather than interleave.
      if (run !== this.pending || !this.roll) return;
      const slice = people.slice(index, index + CHUNK);
      for (const person of slice) this.roll.append(this.entry(person));
      index += CHUNK;
      // setTimeout rather than requestAnimationFrame: rAF does not run in a
      // background tab or under a headless virtual clock, which makes this
      // impossible to test and leaves the roll half-drawn if the reader opens
      // it in a tab they do not look at yet.
      if (index < people.length) window.setTimeout(step, 0);
    };
    step();
  }

  private entry(person: Recordist): HTMLElement {
    const ids = el("p", { className: "credit-ids" });
    person.ids.forEach((id, i) => {
      if (i) ids.append(document.createTextNode(" "));
      ids.append(
        el("a", {
          className: "credit-id",
          text: `XC${id}`,
          attrs: { href: `https://xeno-canto.org/${id}`, rel: "noopener" },
        }),
      );
    });
    return el(
      "section",
      { className: "credit" },
      el("h2", { className: "credit-name", text: person.name }),
      el("p", {
        className: "credit-tally",
        text: `${person.ids.length} recording${person.ids.length === 1 ? "" : "s"}`,
      }),
      ids,
    );
  }
}

void new CreditsPage().load();
