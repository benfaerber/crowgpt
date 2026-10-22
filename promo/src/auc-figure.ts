/**
 * The one chart on the page: one-vs-rest AUC for the two call classes that were
 * label-limited, under weak archive tags versus hand-reviewed crow-tools
 * labels.
 *
 * The four AUCs come from stats.json like every other figure, bundled at build
 * time — the promo page is a static bundle with no API access, and a figure that
 * silently changed when the corpus changed would be a worse promise than a dated
 * one. Those four are hand-entered there: they are a measurement somebody ran,
 * not a row a script can count.
 */

import { num, text } from "./stats";

interface Series {
  key: string;
  label: string;
  note: string;
}

interface Row {
  klass: string;
  values: Record<string, number>;
}

// The segment count is composed into the note rather than written out, so the
// chart and the prose above it cannot come to quote different numbers.
const SERIES: Series[] = [
  { key: "weak", label: "Archive weak tags", note: "free-text `type` field" },
  {
    key: "clean",
    label: "Hand-reviewed labels",
    note: `crow-tools, ${text("crowtools.segments")} segments`,
  },
];

const ROWS: Row[] = [
  { klass: "alarm call", values: { weak: num("auc.alarm.weak"), clean: num("auc.alarm.clean") } },
  { klass: "song", values: { weak: num("auc.song.weak"), clean: num("auc.song.clean") } },
];

/** Where the bars start. AUC below chance is not a meaningful reading. */
const FLOOR = 0.5;
const CEILING = 1.0;

interface Targets {
  chart: Element | null;
  legend: Element | null;
  table: Element | null;
  toggle: Element | null;
}

export class AucFigure {
  private readonly chart: HTMLElement | null;
  private readonly legend: HTMLElement | null;
  private readonly table: HTMLElement | null;
  private readonly toggle: HTMLButtonElement | null;

  constructor(targets: Targets) {
    this.chart = targets.chart as HTMLElement | null;
    this.legend = targets.legend as HTMLElement | null;
    this.table = targets.table as HTMLElement | null;
    this.toggle = targets.toggle as HTMLButtonElement | null;
  }

  render(): void {
    this.renderLegend();
    this.renderChart();
    this.renderTable();
    this.wireToggle();
  }

  private renderLegend(): void {
    if (!this.legend) return;
    this.legend.replaceChildren(
      ...SERIES.map((series, index) => {
        const item = document.createElement("span");
        item.className = "legend-item";
        item.innerHTML =
          `<span class="legend-swatch" data-series="${index + 1}"></span>` +
          `<span class="legend-label">${series.label}</span>` +
          `<span class="legend-note">${series.note}</span>`;
        return item;
      }),
    );
  }

  private renderChart(): void {
    if (!this.chart) return;
    const groups = ROWS.map((row) => {
      const group = document.createElement("div");
      group.className = "bar-group";

      const name = document.createElement("p");
      name.className = "bar-group-name";
      name.textContent = row.klass;
      group.append(name);

      const bars = document.createElement("div");
      bars.className = "bars";
      bars.append(...SERIES.map((series, index) => this.bar(row, series, index + 1)));
      group.append(bars);
      return group;
    });

    const scale = document.createElement("div");
    scale.className = "scale";
    scale.innerHTML =
      `<span class="scale-tick">${FLOOR.toFixed(2)} chance</span>` +
      `<span class="scale-tick scale-tick-end">${CEILING.toFixed(2)} perfect</span>`;

    this.chart.replaceChildren(...groups, scale);
  }

  private bar(row: Row, series: Series, slot: number): HTMLElement {
    const value = row.values[series.key];
    const fraction = (value - FLOOR) / (CEILING - FLOOR);

    const bar = document.createElement("div");
    bar.className = "bar";
    bar.tabIndex = 0;
    bar.setAttribute("role", "img");
    bar.setAttribute("aria-label", `${row.klass}, ${series.label}: AUC ${value.toFixed(2)}`);

    const track = document.createElement("div");
    track.className = "bar-track";
    const fill = document.createElement("div");
    fill.className = "bar-fill";
    fill.dataset.series = String(slot);
    fill.style.setProperty("--fraction", `${(fraction * 100).toFixed(1)}%`);
    track.append(fill);

    const label = document.createElement("span");
    label.className = "bar-value";
    label.textContent = value.toFixed(2);

    const tip = document.createElement("span");
    tip.className = "bar-tip";
    tip.setAttribute("aria-hidden", "true");
    tip.innerHTML =
      `<strong>${row.klass}</strong>` +
      `<span>${series.label}</span>` +
      `<span class="bar-tip-value">AUC ${value.toFixed(2)}</span>`;

    bar.append(track, label, tip);
    return bar;
  }

  private renderTable(): void {
    if (!this.table) return;
    const head = SERIES.map((series) => `<th scope="col">${series.label}</th>`).join("");
    const body = ROWS.map((row) => {
      const cells = SERIES.map((series) => `<td>${row.values[series.key].toFixed(2)}</td>`).join("");
      return `<tr><th scope="row">${row.klass}</th>${cells}</tr>`;
    }).join("");
    this.table.innerHTML =
      `<table><caption>One-vs-rest AUC, American Crow, recording-grouped CV</caption>` +
      `<thead><tr><th scope="col">Class</th>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }

  private wireToggle(): void {
    if (!this.toggle || !this.table) return;
    this.toggle.addEventListener("click", () => {
      const showing = this.table!.hasAttribute("hidden");
      this.table!.toggleAttribute("hidden", !showing);
      this.toggle!.setAttribute("aria-expanded", String(showing));
      this.toggle!.textContent = showing ? "Hide table" : "Show as table";
    });
  }
}
