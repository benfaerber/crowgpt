import { describe, expect, it } from "vitest";

import {
  scoutingAdvice,
  scoutingWindows,
  type DayForecast,
} from "../../src/domain/scoutingWindow";

const at = (h: number, m = 0) => new Date(2026, 7, 21, h, m);

function day(tempAt: (hour: number) => number): DayForecast {
  return {
    hours: Array.from({ length: 24 }, (_, h) => ({
      time: at(h),
      tempC: tempAt(h),
    })),
    sunrise: at(6, 45),
    sunset: at(20, 16),
  };
}

const heatwave = day((h) => (h < 10 ? 24 : h < 21 ? 37 : 30));
const mildDay = day(() => 22);

describe("scoutingWindows", () => {
  it("runs the morning to sunrise+3.5h on a mild day", () => {
    const [morning] = scoutingWindows(mildDay);
    expect(morning.kind).toBe("morning");
    expect(morning.start).toEqual(at(6, 45));
    expect(morning.end).toEqual(at(10, 15));
  });

  it("cuts the morning short when the heat arrives early", () => {
    const [morning] = scoutingWindows(heatwave);
    expect(morning.end).toEqual(at(10));
  });

  it("anchors the evening 90 minutes before sunset, heat or not", () => {
    for (const forecast of [heatwave, mildDay]) {
      const evening = scoutingWindows(forecast).find((w) => w.kind === "evening")!;
      expect(evening.start).toEqual(at(18, 46));
      expect(evening.end).toEqual(at(20, 16));
    }
  });

  it("drops a morning the heat has fully eaten", () => {
    const furnace = day(() => 40);
    const windows = scoutingWindows(furnace);
    expect(windows.map((w) => w.kind)).toEqual(["evening"]);
  });
});

describe("scoutingAdvice", () => {
  it("is good inside the morning window", () => {
    const advice = scoutingAdvice(mildDay, at(8));
    expect(advice.good).toBe(true);
    expect(advice.label).toContain("until");
  });

  it("names the evening window during the midday lull", () => {
    const advice = scoutingAdvice(heatwave, at(13));
    expect(advice.good).toBe(false);
    expect(advice.label).toContain("next window");
  });

  it("says done after sunset", () => {
    const advice = scoutingAdvice(mildDay, at(21));
    expect(advice.good).toBe(false);
    expect(advice.label).toContain("sunrise");
  });
});
