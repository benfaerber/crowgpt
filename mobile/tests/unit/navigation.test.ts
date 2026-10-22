import { describe, expect, it } from "vitest";

import { RouteStack, type Route } from "../../src/app/navigation";
import type { CaptureRecord } from "../../src/domain/types";

const capture = (uuid: string) => ({ uuid }) as CaptureRecord;

const walk = (...routes: Route[]) =>
  routes.reduce((stack, route) => stack.push(route), RouteStack.root());

describe("RouteStack", () => {
  it("starts at the list and refuses to pop past it", () => {
    const root = RouteStack.root();
    expect(root.current).toEqual({ name: "list" });
    expect(root.atRoot).toBe(true);
    expect(root.pop().current).toEqual({ name: "list" });
  });

  it("returns from a capture to the map it was opened from", () => {
    const stack = walk({ name: "map" }, { name: "detail", capture: capture("a") });
    expect(stack.pop().current).toEqual({ name: "map" });
  });

  it("returns from a capture to the list when opened from the list", () => {
    const stack = walk({ name: "detail", capture: capture("a") });
    expect(stack.pop().current).toEqual({ name: "list" });
  });

  it("returns from the logs to whichever screen opened them", () => {
    const fromSettings = walk({ name: "settings" }, { name: "logs" });
    expect(fromSettings.pop().current).toEqual({ name: "settings" });

    const fromHub = walk({ name: "settings" }, { name: "diagnostics" }, { name: "logs" });
    expect(fromHub.pop().current).toEqual({ name: "diagnostics" });
  });

  it("retraces a deep trip one screen at a time", () => {
    let stack = walk(
      { name: "settings" },
      { name: "diagnostics" },
      { name: "headset" },
    );
    expect(stack.current.name).toBe("headset");
    stack = stack.pop();
    expect(stack.current.name).toBe("diagnostics");
    stack = stack.pop();
    expect(stack.current.name).toBe("settings");
    stack = stack.pop();
    expect(stack.atRoot).toBe(true);
  });

  it("returns from creating a family to the capture that asked for one", () => {
    const stack = walk(
      { name: "map" },
      { name: "detail", capture: capture("a") },
      { name: "families" },
    );
    expect(stack.pop().current).toEqual({ name: "detail", capture: capture("a") });
  });

  it("collapses a ping-pong instead of growing the stack", () => {
    const stack = walk(
      { name: "detail", capture: capture("a") },
      { name: "map", focusUuid: "a" },
      { name: "detail", capture: capture("a") },
    );
    expect(stack.current).toEqual({ name: "detail", capture: capture("a") });
    expect(stack.pop().atRoot).toBe(true);
  });

  it("does not collapse a trip to a different capture", () => {
    const stack = walk(
      { name: "detail", capture: capture("a") },
      { name: "map", focusUuid: "a" },
      { name: "detail", capture: capture("b") },
    );
    expect(stack.pop().current).toEqual({ name: "map", focusUuid: "a" });
  });
});
