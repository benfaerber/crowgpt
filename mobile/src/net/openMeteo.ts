import type { DayForecast } from "../domain/scoutingWindow";

/**
 * Today's temperatures and sun times, straight from Open-Meteo.
 *
 * The phone calls the API itself: scouting advice matters precisely when
 * the field server is a home LAN away, and Open-Meteo is keyless. The API
 * returns wall-clock times in the requested zone, which `new Date` parses
 * as device-local — correct as long as the phone is in the valley it is
 * scouting, which is the only place the advice applies anyway.
 */
export async function fetchDayForecast(
  latitude: number,
  longitude: number,
): Promise<DayForecast | undefined> {
  try {
    const url =
      "https://api.open-meteo.com/v1/forecast"
      + `?latitude=${latitude.toFixed(3)}&longitude=${longitude.toFixed(3)}`
      + "&hourly=temperature_2m&daily=sunrise,sunset"
      + "&timezone=auto&forecast_days=1";
    const response = await fetch(url);
    if (!response.ok) return undefined;
    const payload = (await response.json()) as {
      hourly?: { time?: string[]; temperature_2m?: number[] };
      daily?: { sunrise?: string[]; sunset?: string[] };
    };
    const times = payload.hourly?.time ?? [];
    const temps = payload.hourly?.temperature_2m ?? [];
    const sunrise = payload.daily?.sunrise?.[0];
    const sunset = payload.daily?.sunset?.[0];
    if (!sunrise || !sunset || times.length === 0) return undefined;
    return {
      hours: times.map((t, i) => ({ time: new Date(t), tempC: temps[i] ?? 0 })),
      sunrise: new Date(sunrise),
      sunset: new Date(sunset),
    };
  } catch {
    return undefined;
  }
}
