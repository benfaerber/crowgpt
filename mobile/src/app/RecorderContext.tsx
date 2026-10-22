import { createContext, createElement, useContext, type ReactNode } from "react";

import type { AppServices } from "./AppServices";
import type { RecorderView } from "./recorderView";
import { useRecorder } from "./useRecorder";

const RecorderContext = createContext<RecorderView | null>(null);

/**
 * Holds the recorder for the whole app rather than for one screen.
 *
 * This used to be called inside `CaptureListScreen`, which unmounts the moment
 * any other route shows — and it took the earbud-button subscription with it.
 * The MediaSession is claimed by AppServices and outlives every screen, and
 * `RawAudioModule.onMediaButtonEvent` returns true for any key it claims, so a
 * press from Settings was intercepted and then dropped: nothing happened here,
 * and nothing happened in Spotify either. A dead press is worse than an
 * unclaimed button, and from the field it is indistinguishable from the trigger
 * being broken.
 *
 * It also puts the code where its own docstring already said it belonged: the
 * session effect says "hold the mic open for as long as the setting is on — not
 * just this screen", and screen-scoping was surviving only as an unmount
 * side effect. The microphone now closes when the setting says so, or when the
 * app leaves the foreground, and not merely because you opened Settings.
 *
 * A context rather than a prop threaded through every route, because the meter
 * and the buffer clock tick a few times a second: with `children` passed
 * through untouched, React re-renders only the screens that actually read this,
 * instead of every route four times a second while a capture runs.
 */
export function RecorderProvider({
  services,
  onRecorded,
  children,
}: {
  services: AppServices;
  onRecorded: () => void;
  children: ReactNode;
}) {
  const recorder = useRecorder(services, onRecorded);
  return createElement(RecorderContext.Provider, { value: recorder }, children);
}

/** The live recorder. Throws outside the provider rather than handing back a dead one. */
export function useRecorderView(): RecorderView {
  const view = useContext(RecorderContext);
  if (!view) throw new Error("useRecorderView outside RecorderProvider");
  return view;
}
