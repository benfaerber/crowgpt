/** A scanned photo's answer, as the photo worker stores it, and how to read
 *  it. Shared by the promo's Scan page and the operator dashboard, so the two
 *  cannot disagree about what "no bird" means or where the box sits. */

export interface SpeciesScore {
  slug: string;
  common_name: string;
  scientific_name: string;
  probability: number;
}

export interface BirdBox {
  left: number;
  top: number;
  right: number;
  bottom: number;
  /** The detector's own confidence that this is a bird. */
  score?: number;
  birds: number;
}

/** "corvid": a bird was found and judged. "no_bird": none was, and the
 *  ranking is a guess about the whole frame. "other": the photo is of
 *  something else, named in `instead`. */
export type PhotoVerdict = "corvid" | "no_bird" | "other";

export interface PhotoResult {
  ranking: SpeciesScore[];
  /** In pixels of the upright frame, whose size is `width` by `height`. */
  bird_box: BirdBox | null;
  used_location: boolean;
  latitude: number | null;
  longitude: number | null;
  location_source: "exif" | "given" | null;
  width: number;
  height: number;
  verdict?: PhotoVerdict;
  instead?: string | null;
}

/** A rectangle in percentages of its frame, ready for CSS. */
export interface FrameShare {
  left: string;
  top: string;
  width: string;
  height: string;
}

export function percent(probability: number): string {
  const value = probability * 100;
  if (value >= 99.5) return ">99%";
  return value < 1 ? "<1%" : `${Math.round(value)}%`;
}

export class PhotoReading {
  /** How many species a summary lists. The rest are near zero. */
  static readonly SHOWN = 4;

  constructor(readonly result: PhotoResult) {}

  /** Results stored before the verdict existed say it with the box alone. */
  get verdict(): PhotoVerdict {
    return this.result.verdict ?? (this.result.bird_box ? "corvid" : "no_bird");
  }

  get best(): SpeciesScore | undefined {
    return this.result.ranking[0];
  }

  get instead(): string {
    return this.result.instead ?? "something else";
  }

  top(count = PhotoReading.SHOWN): SpeciesScore[] {
    return this.result.ranking.slice(0, count);
  }

  /** Where the judged bird sits in the picture, or null when none was found. */
  get box(): FrameShare | null {
    const box = this.result.bird_box;
    if (!box) return null;
    const { width, height } = this.result;
    return {
      left: `${(box.left / width) * 100}%`,
      top: `${(box.top / height) * 100}%`,
      width: `${((box.right - box.left) / width) * 100}%`,
      height: `${((box.bottom - box.top) / height) * 100}%`,
    };
  }

  get birds(): number {
    return this.result.bird_box?.birds ?? 0;
  }

  /** Coordinates were considered, whether or not they changed the answer. */
  get located(): boolean {
    return this.result.latitude !== null && this.result.longitude !== null;
  }

  place(places = 3): string | undefined {
    return this.located
      ? `${this.result.latitude!.toFixed(places)}, ${this.result.longitude!.toFixed(places)}`
      : undefined;
  }
}
