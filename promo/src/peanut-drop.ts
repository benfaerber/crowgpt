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

/** Where the carried peanut sits in the plain crow's box: the beak meets the
 * peanut there, so swapping to the carrying sprite leaves it where it was. */
const BEAK = new Point(0.975, 0.508);

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
    await this.fly(start, bend, this.target, 1100, "cubic-bezier(0.3, 0, 0.55, 1)");
  }

  async leave(): Promise<void> {
    this.node.classList.add("is-carrying");
    const end = new Point(this.target.x + this.heading * (window.innerWidth * 0.7 + this.width),
      -this.height * 1.5);
    const lift = new Point(this.target.x + this.heading * window.innerWidth * 0.2, this.target.y - 40);
    await this.fly(this.target, lift, end, 1500, "cubic-bezier(0.45, 0, 0.8, 0.6)");
    this.node.remove();
  }

  private async fly(from: Point, via: Point, to: Point, duration: number, easing: string): Promise<void> {
    const frames: Keyframe[] = [];
    const steps = 24;
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      const point = Swooper.bezier(from, via, to, t);
      const ahead = Swooper.bezier(from, via, to, Math.min(1, t + 0.04));
      const behind = Swooper.bezier(from, via, to, Math.max(0, t - 0.04));
      const tilt = Math.atan2(ahead.y - behind.y, Math.abs(ahead.x - behind.x)) * 180 / Math.PI;
      frames.push({ transform: this.transform(point, Math.max(-35, Math.min(35, tilt))) });
    }
    await this.node.animate(frames, { duration, easing, fill: "forwards" }).finished;
  }

  private transform(beak: Point, tilt: number): string {
    const left = beak.x - this.width * BEAK.x;
    const top = beak.y - this.height * BEAK.y;
    return `translate(${left}px, ${top}px) scaleX(${this.heading}) rotate(${tilt}deg)`;
  }

  private static bezier(a: Point, b: Point, c: Point, t: number): Point {
    const u = 1 - t;
    return new Point(u * u * a.x + 2 * u * t * b.x + t * t * c.x, u * u * a.y + 2 * u * t * b.y + t * t * c.y);
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
