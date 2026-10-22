import { describe, expect, it } from "vitest";

import { daySchedule, type DayForecast } from "../../src/domain/scoutingWindow";

const day = (h: number) => new Date(2026, 7, 23, h, 0, 0);

const forecast: DayForecast = {
  sunrise: new Date(2026, 7, 23, 6, 42),
  sunset: new Date(2026, 7, 23, 20, 10),
  hours: Array.from({ length: 24 }, (_, h) => ({
    time: day(h),
    // Cool morning, 38 C mid-afternoon, easing by evening.
    tempC: h < 10 ? 22 : h < 17 ? 38 : 30,
  })),
};

describe("daySchedule", () => {
  const schedule = daySchedule(forecast);
  const at = (h: number) => schedule[h];

  it("night before sunrise and after sunset", () => {
    expect(at(4).state).toBe("night");
    expect(at(21).state).toBe("night");
  });

  it("the morning forage follows sunrise", () => {
    expect(at(7).state).toBe("window");
    expect(at(7).window).toBe("morning");
  });

  it("a 38 degree afternoon is the heat lull", () => {
    expect(at(14).state).toBe("heat");
  });

  it("the evening commute is a window in any weather", () => {
    expect(at(19).state).toBe("window");
    expect(at(19).window).toBe("evening");
  });

  it("a mild hour outside every window is quiet", () => {
    expect(at(17).state).toBe("quiet");
  });

  it("one row per forecast hour", () => {
    expect(schedule).toHaveLength(24);
  });
});
