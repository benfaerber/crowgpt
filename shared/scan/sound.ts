/** A scanned recording's answer, as the sound worker stores it. Shared by the
 *  promo's Scan page and the operator dashboard. */

/** Another species BirdNET heard on the audio. Never context, never a cause. */
export interface CoDetection {
  species: string;
  scientific_name?: string | null;
  confidence: number;
  start?: number;
  end?: number;
}

/** One call region in the analyzer's own words: `start` and `end`, seconds. */
export interface ScanCall {
  start: number;
  end: number;
  species: string;
  scientific_name: string;
  call_type: string | null;
  confidence: number | null;
  crow_conf: number;
  candidate: boolean;
  co_detections?: CoDetection[];
}

export interface SoundResult {
  duration_sec: number;
  waveform: number[];
  calls: ScanCall[];
  co_detections?: CoDetection[];
  truncated: boolean;
  located: boolean;
}

export function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export function describeCoDetection(detection: CoDetection): string {
  return `${detection.species} (${detection.confidence.toFixed(2)})`;
}

/** The one sentence either page says about raptors on the audio, or
 *  undefined when there were none. Worded as a co-detection on purpose. */
export function coDetectionLine(detections: CoDetection[] | undefined): string | undefined {
  if (!detections || detections.length === 0) return undefined;
  return `BirdNET also heard: ${detections.map(describeCoDetection).join(", ")}`;
}
