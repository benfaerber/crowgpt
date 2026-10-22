import type { DayForecast } from "../domain/scoutingWindow";
import type { CaptureRecord } from "../domain/types";

export type Route =
  | { name: "list" }
  | { name: "detail"; capture: CaptureRecord }
  | { name: "settings" }
  | { name: "diagnostics" }
  | { name: "mic-sources" }
  | { name: "headset" }
  | { name: "cues" }
  | { name: "logs" }
  | { name: "guide" }
  | { name: "permissions" }
  | { name: "map"; focusUuid?: string }
  | { name: "scout-schedule"; forecast: DayForecast }
  | { name: "video" }
  | { name: "families" }
  | { name: "labeling"; capture: CaptureRecord };

/**
 * Where "back" goes is wherever you actually came from.
 *
 * The old design was a static parent table, which meant the map -> capture ->
 * back trip landed on the list, and Logs opened from the Diagnostics hub went
 * "back" to Settings. A stack has no opinions: push on open, pop on back, and
 * every trip retraces itself.
 */
export class RouteStack {
  private constructor(private readonly routes: readonly Route[]) {}

  static root(): RouteStack {
    return new RouteStack([{ name: "list" }]);
  }

  get current(): Route {
    return this.routes[this.routes.length - 1];
  }

  /** At the root, Android's back gesture should leave the app. */
  get atRoot(): boolean {
    return this.routes.length === 1;
  }

  /**
   * Ping-pong collapses: opening the screen directly beneath the current one
   * (capture -> "view on map" -> tap the same marker) is going back by another
   * name, so it pops rather than growing the stack forever.
   */
  push(route: Route): RouteStack {
    const beneath = this.routes[this.routes.length - 2];
    if (beneath && sameRoute(beneath, route)) return this.pop();
    return new RouteStack([...this.routes, route]);
  }

  pop(): RouteStack {
    return this.atRoot ? this : new RouteStack(this.routes.slice(0, -1));
  }
}

function sameRoute(a: Route, b: Route): boolean {
  if (a.name !== b.name) return false;
  if (a.name === "detail" || a.name === "labeling")
    return a.capture.uuid === (b as typeof a).capture.uuid;
  if (a.name === "map") return a.focusUuid === (b as typeof a).focusUuid;
  return true;
}
