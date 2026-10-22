/**
 * When crows are worth looking for, computed from sun and temperature.
 *
 * Crows keep photoperiod, not wall time: a foraging peak the first hours
 * after sunrise, a heat-deepened midday lull, and a return-to-territory
 * commute before sunset. The evening anchor is measured, not textbook —
 * Ben's own family returns ~75–90 minutes before sunset (2026-08-20,
 * 7 pm against an 8:18 sunset) — and the heat cutoff matches the day his
 * two nulls fell inside a 38 °C afternoon.
 */

export interface HourTemp {
  time: Date;
  tempC: number;
}

export interface DayForecast {
  hours: HourTemp[];
  sunrise: Date;
  sunset: Date;
}

export interface ScoutingWindow {
  start: Date;
  end: Date;
  kind: "morning" | "evening";
}

/** Corvids trade foraging for shade above this. */
const HOT_C = 35;
const MORNING_HOURS = 3.5;
const EVENING_LEAD_MIN = 90;

export function scoutingWindows(forecast: DayForecast): ScoutingWindow[] {
  const windows: ScoutingWindow[] = [];

  let morningEnd = new Date(
    forecast.sunrise.getTime() + MORNING_HOURS * 3_600_000);
  for (const hour of forecast.hours) {
    if (hour.time <= forecast.sunrise) continue;
    if (hour.tempC >= HOT_C && hour.time < morningEnd) {
      morningEnd = hour.time;
      break;
    }
  }
  if (morningEnd.getTime() - forecast.sunrise.getTime() >= 30 * 60_000) {
    windows.push({ start: forecast.sunrise, end: morningEnd, kind: "morning" });
  }

  // The return commute happens in any weather — dusk is dusk.
  windows.push({
    start: new Date(forecast.sunset.getTime() - EVENING_LEAD_MIN * 60_000),
    end: forecast.sunset,
    kind: "evening",
  });
  return windows;
}

export type HourState = "night" | "window" | "heat" | "quiet";

export interface ScheduleHour {
  time: Date;
  tempC: number;
  state: HourState;
  /** Which window claims the hour, when one does. */
  window?: "morning" | "evening";
}

/**
 * The whole day, hour by hour, as the header advice sees it — what the
 * schedule page renders. A window outranks heat on purpose: the morning
 * window already truncates itself at the first hot hour, and the evening
 * commute happens in any weather — dusk is dusk.
 */
export function daySchedule(forecast: DayForecast): ScheduleHour[] {
  const windows = scoutingWindows(forecast);
  return forecast.hours.map(({ time, tempC }) => {
    const end = new Date(time.getTime() + 3_600_000);
    if (end <= forecast.sunrise || time >= forecast.sunset) {
      return { time, tempC, state: "night" as const };
    }
    const window = windows.find((w) => time < w.end && end > w.start);
    if (window) {
      return { time, tempC, state: "window" as const, window: window.kind };
    }
    if (tempC >= HOT_C) return { time, tempC, state: "heat" as const };
    return { time, tempC, state: "quiet" as const };
  });
}

const clock = (d: Date) =>
  d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });

/** One line for the map header: are the crows likely out right now? */
export function scoutingAdvice(forecast: DayForecast, now: Date): {
  good: boolean;
  label: string;
} {
  const windows = scoutingWindows(forecast);
  for (const w of windows) {
    if (now >= w.start && now <= w.end) {
      return { good: true, label: `Good scouting until ${clock(w.end)}` };
    }
  }
  const next = windows.find((w) => w.start > now);
  if (next) {
    return {
      good: false,
      label: `Quiet hours — next window ${clock(next.start)}–${clock(next.end)}`,
    };
  }
  return { good: false, label: "Done for today — crows again from sunrise" };
}
