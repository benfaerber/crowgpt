import { requireOptionalNativeModule } from "expo";

/** One native crash, as recorded by the process that did not survive it. */
export interface NativeCrash {
  /** Epoch milliseconds, from the phone's clock at the moment it died. */
  at: number;
  thread: string;
  /** The exception class — java.lang.NullPointerException and friends. */
  type: string;
  message: string;
  stack: string;
}

interface CrashLogNative {
  takePendingAsync(): Promise<string[]>;
}

/**
 * Optional on purpose. The module is Android-only and a build without it should
 * degrade to "no native crashes reported", not to an app that will not start —
 * this exists to make failures visible and must not become one.
 */
const native = requireOptionalNativeModule<CrashLogNative>("CrashLog");

/**
 * Crashes recorded since the last time this was asked, taken rather than read.
 *
 * An entry that survived being reported would be reported at every launch
 * forever, and a log that repeats a fortnight-old crash is worse than one that
 * missed it.
 */
export async function takePendingCrashes(): Promise<NativeCrash[]> {
  if (!native) return [];
  try {
    const lines = await native.takePendingAsync();
    return lines.flatMap((line) => {
      try {
        return [JSON.parse(line) as NativeCrash];
      } catch {
        return [];
      }
    });
  } catch {
    return [];
  }
}

export default { takePendingCrashes };
