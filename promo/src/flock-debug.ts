/**
 * Instrumentation for the invisible-crow bug, off unless asked for.
 *
 * Add `?crows=debug` to the URL. Headless Chrome cannot reproduce this — under
 * a virtual clock the animation time never advances, so every bird looks stuck
 * — which means the only place to catch it is a real browser on a real page.
 *
 * The panel matters more than the console here: the bug shows up on a phone,
 * where opening devtools is a chore and the interesting moment has passed by
 * the time you have. Watch the panel, and when a bird vanishes, screenshot it.
 *
 * What to look for when one goes missing:
 *   vis=no with age well under its span  → flying somewhere off screen
 *   anim=0, or state=idle/finished       → the animation died; supervisor is late
 *   rescues climbing                     → something keeps killing crossings
 *   age > span and no rescue             → the supervisor itself is not running
 */

import { el } from "./dom";

interface Row {
  name: string;
  crow: HTMLElement;
  launches: number;
  rescues: number;
  startedAt: number;
  span: number;
}

export class FlockDebug {
  private readonly rows = new Map<HTMLElement, Row>();
  private panel: HTMLElement | null = null;
  private body: HTMLElement | null = null;

  static requested(): boolean {
    return new URLSearchParams(location.search).get("crows") === "debug";
  }

  mount(): void {
    this.panel = el("div", { className: "crow-debug" });
    const title = el("strong", { text: "flock" });
    this.body = el("pre", {});
    this.panel.append(title, this.body);
    document.body.append(this.panel);
    window.setInterval(() => this.render(), 500);
  }

  launched(crow: HTMLElement, name: string, span: number, top: string): void {
    const row = this.rows.get(crow) ?? {
      name,
      crow,
      launches: 0,
      rescues: 0,
      startedAt: 0,
      span: 0,
    };
    row.launches += 1;
    row.startedAt = performance.now();
    row.span = span;
    this.rows.set(crow, row);
    // The animation count is the tell for the pile-up bug: it should be 2 (the
    // wingbeat plus one crossing) and never climb.
    const attached = crow.getAnimations().length;
    console.info(
      `[flock] ${name} launched #${row.launches} span=${Math.round(span / 1000)}s ` +
        `top=${top} anims=${attached}${attached > 2 ? " <-- PILING UP" : ""}`,
    );
  }

  rescued(crow: HTMLElement, name: string, lateBy: number): void {
    const row = this.rows.get(crow);
    if (row) row.rescues += 1;
    console.warn(`[flock] ${name} RESCUED, ${Math.round(lateBy / 1000)}s past its deadline`);
  }

  private render(): void {
    if (!this.body) return;
    const lines: string[] = [];
    for (const row of this.rows.values()) {
      const r = row.crow.getBoundingClientRect();
      const visible =
        r.right > 0 && r.left < window.innerWidth && r.bottom > 0 && r.top < window.innerHeight;
      const anims = row.crow.getAnimations();
      const flight = anims.filter((a) => !(a as CSSAnimation).animationName);
      const age = (performance.now() - row.startedAt) / 1000;
      lines.push(
        [
          row.name.padEnd(9),
          `x=${String(Math.round(r.left)).padStart(5)}`,
          `y=${String(Math.round(r.top)).padStart(4)}`,
          visible ? "vis=yes" : "vis=NO ",
          `age=${age.toFixed(0).padStart(3)}/${Math.round(row.span / 1000)}s`,
          `anim=${flight.length}/${anims.length}${flight[0] ? ":" + flight[0].playState.slice(0, 3) : ""}`,
          `n=${row.launches}`,
          row.rescues ? `RESCUED×${row.rescues}` : "",
        ].join(" "),
      );
    }
    this.body.textContent = lines.join("\n");
  }
}
