/** A scanned recording: its waveform with the detected calls banded over it,
 *  the same picture the app and the dashboard draw, and the calls listed below.
 *
 *  The media element plays the visitor's own file straight from their device;
 *  only the analysis came from the server. Clicking the timeline or a call
 *  seeks it there, so every detection can be checked by ear.
 */

import {
  TimelineGeometry,
  clock,
  coDetectionLine,
  type ScanCall as Call,
  type SoundResult,
} from "../../shared/scan";
import { el } from "./dom";

export type { SoundResult };

/** The call-type colours, as on the front page, the app and the dashboard.
 *  American Crow emits `rattle` rather than `call` (experiment 0012, 0121);
 *  other species heads still carry `call`, and both share the blue swatch.
 */
const CALL_COLOURS: Record<string, string> = {
  "alarm call": "#f27070",
  "flight call": "#6bd28a",
  call: "#6ea8fe",
  rattle: "#6ea8fe",
  begging: "#efb057",
  song: "#c58af9",
};
const NO_TYPE = "var(--text-muted)";

const SVG = "http://www.w3.org/2000/svg";
const WIDTH = 1000;
const HEIGHT = 132;

function svg(tag: string, attrs: Record<string, string | number>): SVGElement {
  const node = document.createElementNS(SVG, tag);
  for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, String(value));
  return node;
}

function colourOf(call: Call): string {
  return (call.call_type && CALL_COLOURS[call.call_type]) || NO_TYPE;
}

function titleCase(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export class ScanTimeline {
  private readonly playhead = svg("rect", { y: 0, width: 2, height: HEIGHT, class: "scan-playhead" });

  private readonly geometry: TimelineGeometry;

  constructor(
    private readonly result: SoundResult,
    private readonly media: HTMLMediaElement,
  ) {
    this.geometry = new TimelineGeometry(result.duration_sec, WIDTH, HEIGHT);
  }

  render(): HTMLElement {
    const calls = this.result.calls;
    const root = el("div", { className: "scan-sound" }, this.media, this.chart());
    root.append(this.axis());
    if (calls.length === 0) {
      root.append(el("p", {
        className: "scan-note",
        text: "No crow, raven or other corvid was found in this recording.",
      }));
    } else {
      root.append(this.legend(), this.list());
    }
    for (const note of this.notes()) root.append(el("p", { className: "scan-note", text: note }));
    this.media.addEventListener("timeupdate", () => this.movePlayhead());
    this.media.addEventListener("seeked", () => this.movePlayhead());
    return root;
  }

  private get span(): number {
    return Math.max(this.result.duration_sec, 0.1);
  }

  private chart(): SVGElement {
    const chart = svg("svg", {
      viewBox: `0 0 ${WIDTH} ${HEIGHT}`,
      preserveAspectRatio: "none",
      class: "scan-timeline",
      role: "img",
      "aria-label": `Waveform with ${this.result.calls.length} detected call regions`,
    });
    for (const call of this.result.calls) {
      const { x, width } = this.geometry.band(call.start, call.end);
      const band = svg("g", {});
      const title = svg("title", {});
      title.textContent = `${this.describe(call)} · ${clock(call.start)}–${clock(call.end)}`;
      band.append(
        title,
        svg("rect", { x, y: 0, width, height: HEIGHT, fill: colourOf(call),
                      opacity: call.candidate ? 0.08 : 0.2 }),
        svg("rect", { x, y: 0, width: 1.5, height: HEIGHT, fill: colourOf(call), opacity: 0.9 }),
      );
      chart.append(band);
    }
    for (const bar of this.geometry.bars(this.result.waveform)) {
      chart.append(svg("rect", { ...bar, class: "scan-bar" }));
    }
    chart.append(this.playhead);
    chart.addEventListener("click", event => {
      const box = chart.getBoundingClientRect();
      this.seek(this.geometry.secondsAt(((event as MouseEvent).clientX - box.left) / box.width));
    });
    return chart;
  }

  private axis(): HTMLElement {
    return el("div", { className: "scan-axis" },
      el("span", { text: "0:00" }),
      el("span", { text: clock(this.span / 2) }),
      el("span", { text: clock(this.span) }));
  }

  private legend(): HTMLElement {
    const present = [...new Set(this.result.calls.map(call => call.call_type))];
    const legend = el("ul", { className: "scan-legend", attrs: { "aria-label": "Call types found" } });
    for (const type of present) {
      const swatch = el("span", { className: "scan-swatch" });
      swatch.style.background = (type && CALL_COLOURS[type]) || NO_TYPE;
      legend.append(el("li", {}, swatch, el("span", { text: type ? titleCase(type) : "Species only" })));
    }
    return legend;
  }

  private list(): HTMLElement {
    const list = el("ol", { className: "scan-calls" });
    for (const call of this.result.calls) {
      const swatch = el("span", { className: "scan-swatch" });
      swatch.style.background = colourOf(call);
      const button = el("button", {
        className: "scan-call",
        attrs: { type: "button", title: "Play from here" },
      },
        el("span", { className: "scan-call-time", text: `${clock(call.start)}–${clock(call.end)}` }),
        swatch,
        el("span", { className: "scan-call-what", text: this.describe(call) }),
        el("span", { className: "scan-call-conf", text: this.certainty(call) }),
      );
      button.addEventListener("click", () => {
        this.seek(call.start);
        void this.media.play().catch(() => undefined);
      });
      list.append(el("li", {}, button));
    }
    return list;
  }

  private describe(call: Call): string {
    const type = call.call_type ? titleCase(call.call_type) : "Call type unknown";
    return `${type} · ${call.species}`;
  }

  private certainty(call: Call): string {
    if (call.candidate) return "maybe a corvid";
    if (call.confidence === null) return "no call-type model for this species";
    return `${Math.round(call.confidence * 100)}% sure of the type`;
  }

  private notes(): string[] {
    const notes: string[] = [];
    const alsoHeard = coDetectionLine(this.result.co_detections);
    if (alsoHeard) notes.push(alsoHeard);
    if (this.result.truncated) {
      notes.push(`Only the first ${Math.round(this.result.duration_sec)} seconds were scanned.`);
    }
    if (this.result.calls.length > 0 && this.result.located) {
      notes.push(
        "Species were limited to those found near your approximate location. For a " +
        "recording made somewhere else, untick the location box and scan it again.",
      );
    }
    if (this.result.calls.length > 0 && !this.result.located) {
      notes.push(
        "No location was sent, so the species is the model's unfiltered guess. It can " +
        "name a look-alike from another continent; the call type is the steadier half.",
      );
    }
    return notes;
  }

  private seek(seconds: number): void {
    this.media.currentTime = seconds;
    this.movePlayhead();
  }

  private movePlayhead(): void {
    this.playhead.setAttribute("x", String(this.geometry.x(this.media.currentTime)));
  }
}
