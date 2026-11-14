/** Click anywhere that is not a control and a peanut drops. It falls under
 * gravity to the bottom fifth of the window, and a crow that was watching
 * swoops down, takes it, and flies off with it.
 *
 * Purely decorative: nothing here is clickable, and with reduced motion asked
 * for there are no peanuts at all.
 */

import { el } from "./dom";

const PEANUT_URL = new URL("./assets/peanut.png", import.meta.url).href;
const GRAVITY = 2600;
const RESTITUTION = 0.28;
const MAX_IN_FLIGHT = 3;
const IGNORE = "a, button, input, select, textarea, label, summary, audio, video, iframe, [role], [contenteditable], .crow, .crow-tip, .photo, .shot, .video, .hero-photo, .lightbox";

class Point {
  constructor(readonly x: number, readonly y: number) {}
}

class Peanut {
  readonly node = el("img", { className: "peanut", attrs: { src: PEANUT_URL, alt: "", "aria-hidden": "true" } });
  private y: number;
  private velocity = 0;
  private angle = Math.random() * 360;
  private readonly spin = (Math.random() - 0.5) * 900;

  constructor(private readonly x: number, from: number, private readonly floor: number) {
    this.y = from;
    this.place();
    document.body.append(this.node);
  }

  get at(): Point {
    return new Point(this.x, this.floor - this.node.offsetHeight / 2);
  }

  fall(): Promise<void> {
    return new Promise((resolve) => {
      let last = performance.now();
      let bounced = false;
      const step = (now: number) => {
        const dt = Math.min(0.05, (now - last) / 1000);
        last = now;
        this.velocity += GRAVITY * dt;
        this.y += this.velocity * dt;
        this.angle += this.spin * dt * (bounced ? 0.3 : 1);
        if (this.y >= this.floor) {
          this.y = this.floor;
          if (bounced || this.velocity < 200) {
            this.place();
            return resolve();
          }
          this.velocity = -this.velocity * RESTITUTION;
          bounced = true;
        }
        this.place();
        requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  }

  remove(): void {
    this.node.remove();
  }

  private place(): void {
    this.node.style.transform = `translate(${this.x}px, ${this.y}px) translate(-50%, -100%) rotate(${this.angle}deg)`;
  }
}

/** A cubic Bézier walked by distance rather than by t, so the easing alone
 * decides the speed and the bird does not surge on the straighter stretches. */
class Path {
  private readonly lengths: number[] = [0];
  private readonly samples: Point[];

  constructor(private readonly a: Point, private readonly b: Point, private readonly c: Point, private readonly d: Point) {
    this.samples = Array.from({ length: 101 }, (_, i) => this.at(i / 100));
    for (let i = 1; i < this.samples.length; i++) {
      const [p, q] = [this.samples[i - 1], this.samples[i]];
      this.lengths.push(this.lengths[i - 1] + Math.hypot(q.x - p.x, q.y - p.y));
    }
  }

  static through(from: Point, via: Point, to: Point): Path {
    const toward = (p: Point, q: Point) => new Point(p.x + (q.x - p.x) * 2 / 3, p.y + (q.y - p.y) * 2 / 3);
    return new Path(from, toward(from, via), toward(to, via), to);
  }

  get length(): number {
    return this.lengths[this.lengths.length - 1];
  }

  /** The point a given fraction of the way along, by distance. */
  along(fraction: number): Point {
    const target = fraction * this.length;
    let i = 1;
    while (i < this.lengths.length - 1 && this.lengths[i] < target) i++;
    const span = this.lengths[i] - this.lengths[i - 1] || 1;
    const t = (i - 1 + (target - this.lengths[i - 1]) / span) / 100;
    return this.at(Math.min(1, t));
  }

  private at(t: number): Point {
    const u = 1 - t;
    const [w0, w1, w2, w3] = [u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t];
    return new Point(
      w0 * this.a.x + w1 * this.b.x + w2 * this.c.x + w3 * this.d.x,
      w0 * this.a.y + w1 * this.b.y + w2 * this.c.y + w3 * this.d.y,
    );
  }
}

/** Where the carried peanut sits in the plain crow's box: the beak meets the
 * peanut there, so swapping to the carrying sprite leaves it where it was. */
const BEAK = new Point(0.975, 0.508);
const CARRY_SPEED = 300;

class Swooper {
  readonly node = el("div", { className: "peanut-crow", attrs: { "aria-hidden": "true" } });
  private readonly width = 120;
  private readonly height = this.width * 180 / 130;
  private readonly heading: 1 | -1;

  constructor(private readonly target: Point) {
    this.heading = target.x > window.innerWidth / 2 ? -1 : 1;
    this.node.style.setProperty("--w", `${this.width}px`);
    document.body.append(this.node);
  }

  async swoop(): Promise<void> {
    const start = new Point(this.target.x - this.heading * (window.innerWidth * 0.6 + this.width),
      -this.height - Math.random() * window.innerHeight * 0.1);
    const bend = new Point(this.target.x - this.heading * window.innerWidth * 0.15, this.target.y - 30);
    await this.fly(Path.through(start, bend, this.target), 1100, "cubic-bezier(0.3, 0, 0.55, 1)", 35);
  }

  /** Laden, so a low takeoff that climbs gradually and leaves by the side, not
   * a rocket to the top corner. */
  async leave(): Promise<void> {
    this.node.classList.add("is-carrying");
    const height = window.innerHeight;
    const from = this.target;
    const exitX = this.heading > 0 ? window.innerWidth + this.width * 1.2 : -this.width * 1.2;
    const exitY = Math.max(height * 0.08, from.y - height * (0.12 + Math.random() * 0.08));
    const run = exitX - from.x;
    const path = new Path(
      from,
      new Point(from.x + run * 0.3, from.y - 12),
      new Point(from.x + run * 0.65, from.y - (from.y - exitY) * 0.5),
      new Point(exitX, exitY),
    );
    const duration = Math.min(5000, Math.max(2200, path.length / CARRY_SPEED * 1000));
    await this.fly(path, duration, "cubic-bezier(0.45, 0, 0.75, 0.8)", 20);
    this.node.remove();
  }

  private async fly(path: Path, duration: number, easing: string, maxTilt: number): Promise<void> {
    const steps = 40;
    const frames: Keyframe[] = [];
    for (let i = 0; i <= steps; i++) {
      const fraction = i / steps;
      const ahead = path.along(Math.min(1, fraction + 0.03));
      const behind = path.along(Math.max(0, fraction - 0.03));
      const tilt = Math.atan2(ahead.y - behind.y, Math.abs(ahead.x - behind.x)) * 180 / Math.PI;
      frames.push({ transform: this.transform(path.along(fraction), Math.max(-maxTilt, Math.min(maxTilt, tilt))) });
    }
    await this.node.animate(frames, { duration, easing, fill: "forwards" }).finished;
  }

  private transform(beak: Point, tilt: number): string {
    const left = beak.x - this.width * BEAK.x;
    const top = beak.y - this.height * BEAK.y;
    return `translate(${left}px, ${top}px) scaleX(${this.heading}) rotate(${tilt}deg)`;
  }
}

export class PeanutDrop {
  private inFlight = 0;

  mount(): void {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    document.addEventListener("click", (event) => this.onClick(event));
  }

  private onClick(event: MouseEvent): void {
    if (event.defaultPrevented || event.button !== 0) return;
    if (this.inFlight >= MAX_IN_FLIGHT) return;
    if (event.target instanceof Element && event.target.closest(IGNORE)) return;
    if (String(window.getSelection() ?? "").length > 0) return;
    void this.drop(event.clientX, event.clientY);
  }

  private async drop(x: number, y: number): Promise<void> {
    this.inFlight++;
    const height = window.innerHeight;
    const floor = Math.min(height - 12, Math.max(y + 16, height * (0.82 + Math.random() * 0.13)));
    const peanut = new Peanut(x, y, floor);
    try {
      await peanut.fall();
      await PeanutDrop.pause(250 + Math.random() * 400);
      const crow = new Swooper(peanut.at);
      await crow.swoop();
      peanut.remove();
      await crow.leave();
    } finally {
      peanut.remove();
      this.inFlight--;
    }
  }

  private static pause(ms: number): Promise<void> {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }
}
