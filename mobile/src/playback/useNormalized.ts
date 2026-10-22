import { useEffect, useState } from "react";

import { describeGain } from "../domain/gain";
import type { AppServices } from "../app/AppServices";
import { log } from "../app/Log";

export interface NormalizedView {
  /** What to give the player. The original recording until the copy is ready. */
  uri: string;
  /** "+18 dB", or undefined when nothing was worth changing. */
  note?: string;
  /** True while the louder copy is being made. */
  working: boolean;
  /** The recording is quieter than the boost ceiling can fix. */
  atCeiling: boolean;
}

/**
 * The listenable version of a capture.
 *
 * Starts on the original so the play button never waits on a file being
 * written, and swaps as soon as the louder copy exists. Any failure — an
 * unreadable file, a format the parser does not know — leaves the original
 * playing rather than nothing at all.
 */
export function useNormalized(
  services: AppServices,
  audioPath: string | undefined,
  enabled: boolean,
): NormalizedView {
  const original = audioPath
    ? audioPath.startsWith("file://")
      ? audioPath
      : `file://${audioPath}`
    : "";
  const [view, setView] = useState<NormalizedView>({ uri: original, working: false, atCeiling: false });

  useEffect(() => {
    setView({ uri: original, working: enabled && !!audioPath, atCeiling: false });
    if (!audioPath || !enabled) return;
    let live = true;
    void services.normalized
      .of(audioPath)
      .then((result) => {
        if (!live) return;
        setView({
          uri: result.uri,
          note: describeGain(result.plan),
          working: false,
          atCeiling: result.plan.atCeiling,
        });
      })
      .catch((failure) => {
        // The quiet fallback is right — a capture that cannot be boosted
        // must still play — but the reason it happened should not vanish
        // with it.
        log.warn("playback", "normalisation failed; playing the original", failure);
        return live && setView({ uri: original, working: false, atCeiling: false });
      });
    return () => {
      live = false;
    };
  }, [audioPath, enabled, original, services]);

  return view;
}
