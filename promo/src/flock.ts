/**
 * The Poe family, flying across the top of the page.
 *
 * Five named birds rather than five copies of one bird: each crosses on its own
 * undulating path, and when it leaves the frame it comes back somewhere else,
 * so the sky never settles into a loop you can watch repeating.
 *
 * Sizes are relative and deliberate — fledglings smallest, the yearling between
 * them and the parents, the parents largest.
 *
 * The caws are real field recordings, cut from spans a human labeled by ear.
 * Only Edgar's are attributable to a named bird — the recordist's own capture
 * says so — the rest are matched by call type to what that bird would be doing:
 * begging for the fledglings, alarm calls for the adults. No label in the
 * database attributes a call to any other individual, and this does not invent
 * one.
 */

import { el } from "./dom";
import { FlockDebug } from "./flock-debug";

/** Whatever is showing the page's media — the lightbox, in practice. */
export interface Viewer {
  openFigure(figure: HTMLElement): boolean;
}

const caw = (file: string) => new URL(`./assets/caws/${file}`, import.meta.url).href;

export interface Bird {
  name: string;
  role: string;
  note: string;
  /** Relative width; the parents are the reference at 1. */
  size: number;
  calls: string[];
  /** What the audio actually is, said plainly in the tooltip. */
  callNote: string;
  /**
   * The id of a figure on this page that shows this bird, opened in the
   * lightbox from the tooltip.
   *
   * Held to the same standard as the calls above: only where a photograph is
   * actually attributable. Some birds have none — the family is hard to tell
   * apart by eye, and a name under the wrong bird is worse than a gap. This one
   * has been wrong twice already, in both directions.
   */
  photo?: string;
  /**
   * Said under the button when the media shows more than this one bird.
   *
   * A group clip is still worth reaching from a name, but "See Ripjaw" opening
   * four crows on a post has to admit which of them is Ripjaw is not something
   * anybody here can tell you.
   */
  photoNote?: string;
}

export const POE_FAMILY: Bird[] = [
  {
    name: "Thrasher",
    role: "Parent",
    note: "One of the two parents, and Ripjaw's mate. Sex not yet confirmed.",
    size: 1,
    calls: [caw("adult-alarm-a.mp3"), caw("adult-alarm-c.mp3")],
    callNote: "Alarm call, recorded in the field",
    photo: "photo-thrasher",
  },
  {
    name: "Ripjaw",
    role: "Parent",
    note: "The other parent, and Thrasher's mate. Sex not yet confirmed.",
    size: 1,
    // Cut from the two most distant captures in the set — an unseen crow calling
    // out of view, and the family thirty metres up on the roofline. The clips
    // Ripjaw had before caught Ben talking underneath the birds.
    calls: [caw("ripjaw-alarm-a.mp3"), caw("ripjaw-alarm-b.mp3")],
    callNote: "Alarm call, recorded in the field",
    photo: "photo-ripjaw",
  },
  {
    name: "Edgar",
    role: "Brood guard",
    note: "Named after Edgar Allan Poe. I know that's the raven, but it still felt fitting. A yearling from a previous brood who stayed on instead of leaving. He is the security guard, watching the others from some lookout spot. Nothing gets past him.",
    size: 0.88,
    calls: [caw("edgar-alarm.mp3")],
    callNote: "Edgar himself, on top of the office",
    photo: "photo-edgar",
  },
  {
    name: "Killer",
    role: "Fledgling",
    note: "One of this year's two fledglings, and the friendly one: he often flies over and caws back when I say hi, or bye.",
    size: 0.78,
    calls: [caw("fledgling-beg-a.mp3")],
    callNote: "Begging call, recorded in the field",
    photo: "photo-killer",
  },
  {
    name: "Shredder",
    role: "Fledgling",
    note: "The other fledgling, and Killer's sibling.",
    size: 0.78,
    calls: [caw("fledgling-beg-b.mp3")],
    callNote: "Begging call, recorded in the field",
    photo: "photo-shredder",
    photoNote: "The peanut clip with Killer and Edgar. Shredder is one of the three.",
  },
];

const BASE_WIDTH = 74;
const SAMPLES = 48;

function between(low: number, high: number): number {
  return low + Math.random() * (high - low);
}

export class Flock {
  private readonly sky: HTMLElement | null;
  private tooltip: HTMLElement | null = null;
  private playing: HTMLAudioElement | null = null;
  private held: HTMLElement | null = null;
  private readonly deadlines = new Map<HTMLElement, number>();
  private readonly flights = new Map<HTMLElement, Animation>();
  private readonly flock: HTMLElement[] = [];
  private discovered = false;
  private hintDelay = 0;
  private hintTick = 0;
  private readonly watch = FlockDebug.requested() ? new FlockDebug() : null;
  private thaw = 0;
  private leaving = 0;

  constructor(
    selector: string,
    private readonly viewer?: Viewer,
    private readonly birds: Bird[] = POE_FAMILY,
  ) {
    this.sky = document.querySelector(selector);
  }

  mount(): void {
    if (!this.sky) return;

    // On the body rather than inside the sky: the sky sits behind the hero text
    // so the birds fly under it, and a tooltip parented there inherits that and
    // opens behind the words it is meant to be read over.
    this.tooltip = document.createElement("div");
    this.tooltip.className = "crow-tip";
    this.tooltip.hidden = true;
    document.body.append(this.tooltip);

    this.watch?.mount();
    this.watchForLostPointer();
    this.superviseFlock();

    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    this.birds.forEach((bird, index) => {
      const crow = document.createElement("span");
      crow.className = "crow";
      crow.style.setProperty("--w", `${Math.round(BASE_WIDTH * bird.size)}px`);
      crow.style.setProperty("--flap", `${(0.62 + (1 - bird.size) * 0.5).toFixed(2)}s`);
      crow.setAttribute("role", "button");
      crow.setAttribute("aria-label", `${bird.name}, ${bird.role.toLowerCase()}: hear a caw`);
      crow.tabIndex = 0;

      crow.addEventListener("pointerenter", () => {
        this.cancelRelease();
        this.freeze(crow, true);
        this.showTip(bird, crow);
      });
      // Scheduled, not immediate: there is a gap between the bird and its
      // tooltip, and letting go the instant the pointer leaves the bird makes
      // the tooltip's own button impossible to reach.
      crow.addEventListener("pointerleave", () => this.scheduleRelease());
      crow.addEventListener("focus", () => {
        this.cancelRelease();
        this.freeze(crow, true);
        this.showTip(bird, crow);
      });
      crow.addEventListener("blur", () => this.scheduleRelease());
      crow.addEventListener("click", () => this.play(bird));
      crow.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          this.play(bird);
        }
      });

      crow.dataset.bird = bird.name;
      this.sky!.append(crow);
      this.flock.push(crow);

      if (still) {
        // Parked rather than hidden: the birds are labeled, clickable content
        // now, so someone who turned motion off still gets to meet them.
        crow.style.top = `${10 + index * 7}%`;
        crow.style.left = `${6 + index * 15}%`;
        crow.style.backgroundPosition = `${index * 11}% 0`;
        return;
      }
      this.launch(crow, true);
    });

    this.inviteWhenIdle();
  }

  /**
   * After a while, gild whichever bird is currently on screen.
   *
   * Nothing about a crow drifting past says "press me", so someone can read the
   * whole page without ever learning the birds are the family and that each one
   * has a voice. The hint waits rather than shouting: if it appeared straight
   * away it would compete with the headline, which is what people came for.
   *
   * It stops for good the moment a caw is played — the invitation has done its
   * job and repeating it would be nagging.
   */
  private inviteWhenIdle(): void {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    this.hintDelay = window.setTimeout(() => {
      this.offerHint();
      // Re-picked as birds cross out of view: a glow on a bird that has already
      // left the screen is an invitation nobody can see.
      this.hintTick = window.setInterval(() => this.offerHint(), 2500);
    }, 12000);
  }

  private offerHint(): void {
    if (this.discovered) return;
    const visible = this.flock.find((crow) => {
      const r = crow.getBoundingClientRect();
      return r.left > 24 && r.right < window.innerWidth - 24 && r.top > 0 && r.bottom < window.innerHeight;
    });
    for (const crow of this.flock) crow.classList.toggle("is-inviting", crow === visible);
  }

  /** The user found them. Stop hinting, permanently. */
  private stopHinting(): void {
    this.discovered = true;
    window.clearTimeout(this.hintDelay);
    window.clearInterval(this.hintTick);
    for (const crow of this.flock) crow.classList.remove("is-inviting");
  }

  /**
   * Send a bird across on an undulating path, then do it again somewhere else.
   *
   * A straight line reads as a sprite being slid across; real flight rises and
   * falls with the wingbeat. The path is a sine sampled into keyframes, with a
   * random amplitude, wavelength and phase per crossing, plus an overall drift
   * so it does not arrive at the height it left.
   */
  private launch(crow: HTMLElement, first = false): void {
    const duration = between(17000, 31000);
    const amplitude = between(6, 26);
    const waves = between(1.5, 4);
    const phase = Math.random() * Math.PI * 2;
    const drift = between(-40, 30);

    // Kept to the band of open sky above the headline. Given the run of the
    // whole hero the birds land over the photo and the stat row, which reads as
    // a sprite loose on the page rather than crows in the air.
    //
    // The starting height has to clear the worst upward excursion of the path,
    // because .sky clips at its edges: a bird starting at 4% that then rides the
    // sine up and drifts up as well leaves the layer entirely and is cut out of
    // existence mid-flight. Reserve that much room before choosing a top.
    const headroom = amplitude + Math.max(0, -drift) + 6;
    const skyHeight = this.sky?.clientHeight ?? 600;
    // Bounded by the window as well as by the sky. The sky is the whole hero —
    // around 1600px once the photo and the stat row are in it — so a share of
    // *that* puts birds 500px down, past the headline and off the bottom of a
    // phone screen. They are still flying; you just cannot see them, which
    // looks exactly like disappearing.
    const visible = Math.min(skyHeight, window.innerHeight);
    // Tighter on a phone: there the open sky is only the strip above the
    // headline, and birds crossing the words themselves make them hard to read
    // on the screen where reading is already hardest.
    const cap = window.innerWidth < 700 ? 210 : 420;
    const lowest = Math.max(headroom, Math.min(skyHeight * 0.36, visible * 0.42, cap));
    crow.style.top = `${between(headroom, lowest).toFixed(0)}px`;

    const frames = Array.from({ length: SAMPLES + 1 }, (_, i) => {
      const t = i / SAMPLES;
      const x = -25 + t * 150;
      const y = Math.sin(phase + t * waves * Math.PI * 2) * amplitude + drift * t;
      return { transform: `translate3d(${x.toFixed(2)}vw, ${y.toFixed(2)}px, 0)`, offset: t };
    });

    // fill "both", not "backwards": once a crossing ends the transform stops
    // applying, and the bird snaps back to left: 0 — parked in the middle of
    // the headline for the whole pause before it flies again. Holding the last
    // keyframe keeps it off the right-hand edge until it re-enters.
    // When this crossing should be over. The supervisor uses it to notice a bird
    // that has stopped making progress, whatever the reason.
    this.deadlines.set(crow, performance.now() + duration + 8000);

    this.watch?.launched(crow, crow.dataset.bird ?? "?", duration, crow.style.top);

    // Cancel the one before it. A finished animation with fill:both is still
    // attached to the element, and Firefox keeps handing it back from
    // getAnimations() — so without this they pile up, and each one that gets
    // restarted drags the bird back to the left edge it started from.
    this.flights.get(crow)?.cancel();

    const flight = crow.animate(frames, { duration, easing: "linear", fill: "both" });
    this.flights.set(crow, flight);
    // On the first pass only, drop each bird in partway across, so the page does
    // not open with an empty sky and five birds arriving together.
    if (first) flight.currentTime = Math.random() * duration;
    flight.addEventListener("finish", () => {
      // Only the crossing that is still the current one may schedule the next.
      // A stale animation finishing would otherwise start a second chain, and
      // the two would take turns resetting the bird to the left edge.
      if (this.flights.get(crow) !== flight) return;
      // A short, varied pause before it comes back, so the five never fall into
      // step with each other. Kept brief — during the gap the bird is parked
      // off the right edge, which reads as one having gone missing.
      window.setTimeout(() => this.launch(crow), between(300, 2200));
    });
  }

  /**
   * Put back any bird that has stopped flying, whatever stopped it.
   *
   * Three separate real bugs have grounded these birds — clipping out of the
   * sky, a hover that never thawed, a band that ran off the bottom of the
   * screen — and each fix was correct without being the whole story. Rather
   * than keep guessing at the fourth, this watches for the symptom directly: a
   * crossing that has outlived its own duration by a wide margin is not going
   * to finish, so start a fresh one.
   *
   * A supervisor, not a diagnosis. One cheap check every two seconds, and the
   * failure becomes self-correcting instead of permanent.
   */
  private superviseFlock(): void {
    window.setInterval(() => {
      const now = performance.now();
      for (const [crow, deadline] of this.deadlines) {
        // A held bird is paused on purpose; its clock should not run down.
        if (crow === this.held) {
          this.deadlines.set(crow, deadline + 2000);
          continue;
        }
        if (now > deadline) {
          this.watch?.rescued(crow, crow.dataset.bird ?? "?", now - deadline);
          this.launch(crow);
        }
      }
    }, 2000);
  }

  /**
   * Hold a bird still while it is being looked at, wingbeat and all.
   *
   * Freezing is easy; the hard part is guaranteeing it thaws. A paused bird
   * never reaches the end of its crossing, so it never fires `finish` and never
   * relaunches — it just stops, permanently, and the flock loses a member. That
   * happens whenever `pointerleave` goes missing: the pointer leaves the window
   * in one jump, another element swallows it, the tab changes. So nothing here
   * depends on that one event arriving — see releaseHeld().
   */
  private freeze(crow: HTMLElement, held: boolean): void {
    if (held) {
      if (this.held && this.held !== crow) this.freeze(this.held, false);
      this.held = crow;
      window.clearTimeout(this.thaw);
      // Last resort. Whatever else fails, a bird is never held for longer than
      // someone would plausibly be looking at it.
      this.thaw = window.setTimeout(() => this.releaseHeld(), 10000);
    } else if (this.held === crow) {
      this.held = null;
      window.clearTimeout(this.thaw);
    }

    crow.classList.toggle("is-held", held);
    for (const animation of crow.getAnimations()) {
      if (held) {
        if (animation.playState === "running") animation.pause();
      } else if (animation.playState === "paused") {
        // Only what this freeze actually paused. play() on a *finished*
        // animation rewinds it to the beginning and runs it again, which
        // teleports the bird back off the left edge and fires a second finish.
        animation.play();
      }
    }
  }

  private releaseHeld(): void {
    this.cancelRelease();
    if (this.held) this.freeze(this.held, false);
    this.hideTip();
  }

  /** Let go shortly, unless the pointer arrives on the bird or its tooltip. */
  private scheduleRelease(): void {
    window.clearTimeout(this.leaving);
    this.leaving = window.setTimeout(() => this.releaseHeld(), 260);
  }

  private cancelRelease(): void {
    window.clearTimeout(this.leaving);
    this.leaving = 0;
  }

  /** True while the pointer is somewhere that should keep the tooltip open. */
  private within(node: Node | null): boolean {
    if (!node) return false;
    return Boolean(this.held?.contains(node)) || Boolean(this.tooltip?.contains(node));
  }

  /** Ways a bird can stop being hovered that do not involve a pointerleave. */
  private watchForLostPointer(): void {
    document.addEventListener(
      "pointermove",
      (event) => {
        if (!this.held) return;
        if (this.within(event.target as Node | null)) this.cancelRelease();
        else this.scheduleRelease();
      },
      { passive: true },
    );
    this.tooltip?.addEventListener("pointerenter", () => this.cancelRelease());
    this.tooltip?.addEventListener("pointerleave", () => this.scheduleRelease());
    document.addEventListener("pointercancel", () => this.releaseHeld());
    window.addEventListener("blur", () => this.releaseHeld());
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) this.releaseHeld();
    });
  }

  private play(bird: Bird): void {
    this.stopHinting();
    const src = bird.calls[Math.floor(Math.random() * bird.calls.length)];
    this.playing?.pause();
    const audio = new Audio(src);
    audio.volume = 0.85;
    this.playing = audio;
    void audio.play().catch(() => {
      /* A browser that refuses to play without a gesture is not an error here. */
    });
  }

  /**
   * A real button rather than an instruction.
   *
   * "Click the bird to play a caw" asks someone to hit a moving target, and the
   * earlier wording sent people toward the tooltip — which was not a target at
   * all and vanished as they set off. A button that stays put under the pointer
   * is the thing they were already trying to press.
   */
  private playButton(bird: Bird): HTMLButtonElement {
    const button = el("button", {
      className: "crow-tip-play",
      attrs: { type: "button" },
    });
    button.append(
      el("span", { className: "crow-tip-play-icon", text: "▶" }),
      el("span", { text: `Play ${bird.name}'s caw` }),
    );
    button.addEventListener("click", () => this.play(bird));
    return button;
  }

  /**
   * The other half of meeting a bird: hear it, then see it.
   *
   * The photograph is already on the page further down, so this opens the
   * lightbox by clicking that figure's image — the viewer the rest of the page
   * uses, with its own slide order and arrows, rather than a second one that
   * would behave differently. The bird is let go first: leaving a frozen crow
   * and a tooltip under a full-screen overlay is how you come back to a hero
   * that has quietly stopped.
   */
  private photoButton(bird: Bird): HTMLButtonElement | null {
    if (!bird.photo || !this.viewer) return null;
    const figure = document.getElementById(bird.photo);
    if (!figure) return null;

    const button = el("button", {
      className: "crow-tip-photo",
      attrs: { type: "button" },
    });
    button.append(
      el("span", { className: "crow-tip-play-icon", text: "◆" }),
      el("span", { text: bird.photoNote ? `See the clip` : `See ${bird.name}` }),
    );
    button.addEventListener("click", () => {
      this.releaseHeld();
      this.viewer!.openFigure(figure);
    });
    return button;
  }

  private showTip(bird: Bird, crow: HTMLElement): void {
    if (!this.tooltip) return;
    const photo = this.photoButton(bird);
    const parts: Node[] = [
      el("strong", { text: bird.name }),
      el("span", { className: "crow-tip-role", text: bird.role }),
      el("p", { text: bird.note }),
      el("div", { className: "crow-tip-actions" }, this.playButton(bird), photo),
      el("p", { className: "crow-tip-source", text: bird.callNote }),
    ];
    if (photo && bird.photoNote) {
      parts.push(el("p", { className: "crow-tip-source", text: bird.photoNote }));
    }
    // Said rather than left blank, for the same reason the calls say what they
    // are: the reader should know the gap is honest, not an oversight.
    if (!photo) {
      parts.push(
        el("p", {
          className: "crow-tip-source",
          text: "No photo pinned to this one. They are hard to tell apart in a photograph.",
        }),
      );
    }
    this.tooltip.replaceChildren(...parts);
    this.tooltip.hidden = false;

    const at = crow.getBoundingClientRect();
    const tip = this.tooltip.getBoundingClientRect();
    const half = tip.width / 2;
    const left = Math.min(
      Math.max(at.left + at.width / 2, half + 8),
      window.innerWidth - half - 8,
    );
    // Below the bird normally, above it when the bird is low enough that the
    // tooltip would run off the bottom of the window.
    const below = at.bottom + 10;
    const fits = below + tip.height < window.innerHeight - 8;
    this.tooltip.style.left = `${left}px`;
    this.tooltip.style.top = `${fits ? below : at.top - tip.height - 10}px`;
  }

  private hideTip(): void {
    if (this.tooltip) this.tooltip.hidden = true;
  }
}
