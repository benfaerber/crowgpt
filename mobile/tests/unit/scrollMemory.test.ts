import { describe, expect, it } from "vitest";

import { ScrollMemory } from "../../src/ui/useRememberedScroll";

describe("ScrollMemory", () => {
  it("starts every screen at the top", () => {
    expect(new ScrollMemory().recall("settings")).toBe(0);
  });

  it("recalls the last saved offset per screen", () => {
    const memory = new ScrollMemory();
    memory.save("settings", 480);
    memory.save("settings", 620);
    memory.save("list", 90);
    expect(memory.recall("settings")).toBe(620);
    expect(memory.recall("list")).toBe(90);
  });

  it("forgets a screen without touching the others", () => {
    const memory = new ScrollMemory();
    memory.save("settings", 480);
    memory.save("list", 90);
    memory.forget("settings");
    expect(memory.recall("settings")).toBe(0);
    expect(memory.recall("list")).toBe(90);
  });
});
