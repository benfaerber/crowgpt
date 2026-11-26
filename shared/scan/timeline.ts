/** Where things go on a waveform drawn across a fixed box: the bars, a
 *  call's band, the playhead. The app, the dashboard and the promo all draw
 *  this picture, and the arithmetic is the part that must not drift. */

export interface Bar {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Band {
  x: number;
  width: number;
}

export class TimelineGeometry {
  /** Room left above and below the tallest bar. */
  private static readonly MARGIN = 8;

  constructor(
    readonly duration: number,
    readonly width: number,
    readonly height: number,
  ) {}

  private get span(): number {
    return Math.max(this.duration, 0.1);
  }

  /** Bars, not a filled path: a peak envelope is a series of maxima, and
   *  interpolating between them draws a shape the audio never had. */
  bars(peaks: number[]): Bar[] {
    const step = this.width / Math.max(peaks.length, 1);
    return peaks.map((peak, index) => {
      const height = Math.max(1, Math.min(1, peak) * (this.height - TimelineGeometry.MARGIN));
      return {
        x: index * step,
        y: this.height / 2 - height / 2,
        width: Math.max(0.5, step * 0.8),
        height,
      };
    });
  }

  band(start: number, end: number): Band {
    return {
      x: this.x(start),
      width: Math.max(2, ((end - start) / this.span) * this.width),
    };
  }

  x(seconds: number): number {
    return (Math.max(0, Math.min(seconds, this.span)) / this.span) * this.width;
  }

  /** The time under a click, given how far across the drawn box it landed. */
  secondsAt(fraction: number): number {
    return Math.max(0, Math.min(1, fraction)) * this.span;
  }
}
