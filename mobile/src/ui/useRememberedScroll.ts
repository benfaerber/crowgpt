import { useCallback, useRef } from "react";
import type { NativeScrollEvent, NativeSyntheticEvent, ScrollView } from "react-native";

/**
 * Session-scoped scroll offsets, keyed by screen.
 *
 * Screens unmount on every navigation, so Settings -> App Log -> back landed
 * at the top of Settings instead of beside the App Log row. The stack now
 * remembers where you were; this remembers where you were *looking*.
 *
 * Deliberately not persisted: a restart starting every screen at the top is
 * correct, for the same reason the capture filter is session-scoped.
 */
export class ScrollMemory {
  private offsets = new Map<string, number>();

  save(key: string, y: number): void {
    this.offsets.set(key, y);
  }

  recall(key: string): number {
    return this.offsets.get(key) ?? 0;
  }

  /** Opening a screen fresh starts at the top; only returning restores. */
  forget(key: string): void {
    this.offsets.delete(key);
  }
}

export const scrollMemory = new ScrollMemory();

/**
 * Spread onto a ScrollView (or KeyboardAwareScroll) to give it a memory.
 *
 * Restoring happens on content-size changes rather than mount, because
 * screens that load their content async (the log, the capture list) have
 * nothing to scroll to at mount time. It keeps re-applying as the content
 * grows until the recordist touches the screen, whose gesture then owns the
 * position.
 */
export function useRememberedScroll(key: string) {
  const ref = useRef<ScrollView>(null);
  const touched = useRef(false);

  const onScroll = useCallback(
    (event: NativeSyntheticEvent<NativeScrollEvent>) => {
      scrollMemory.save(key, event.nativeEvent.contentOffset.y);
    },
    [key],
  );

  const onScrollBeginDrag = useCallback(() => {
    touched.current = true;
  }, []);

  const onContentSizeChange = useCallback(() => {
    if (touched.current) return;
    const y = scrollMemory.recall(key);
    if (y > 0) ref.current?.scrollTo({ y, animated: false });
  }, [key]);

  return { ref, onScroll, onScrollBeginDrag, onContentSizeChange, scrollEventThrottle: 16 };
}
