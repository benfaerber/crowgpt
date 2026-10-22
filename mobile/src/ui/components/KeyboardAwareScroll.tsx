import { forwardRef, useEffect, useRef } from "react";
import {
  ScrollView,
  TextInput,
  useWindowDimensions,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  type ScrollViewProps,
} from "react-native";

import { useKeyboardInset } from "../useKeyboardInset";

/** How much clear space to leave under a focused field. */
const MARGIN = 24;

/**
 * A ScrollView that keeps the focused field above the keyboard.
 *
 * Every screen was solving this separately and most were not solving it at all.
 * The pattern had been: a keyboard inset for padding, plus an `onStartEditing`
 * prop threaded from the screen into each individual editor so it could scroll
 * itself into view. That works exactly as far as somebody remembers to wire it,
 * and typing into "Seen nearby" put the field under the keyboard because nobody
 * had.
 *
 * So it is done here instead, for anything inside: on keyboard show, find
 * whichever input is focused, measure where it actually is, and scroll only if
 * it is covered. No per-field wiring, and nothing to remember when adding the
 * next text box.
 *
 * Padding as well as scrolling, because the app draws edge-to-edge — which
 * stops Android's adjustResize from shrinking the window, so without it the
 * content has nowhere to scroll *to*.
 */
export const KeyboardAwareScroll = forwardRef<ScrollView, ScrollViewProps>(
  function KeyboardAwareScroll({ contentContainerStyle, onScroll, ...props }, ref) {
    const inner = useRef<ScrollView | null>(null);
    const offset = useRef(0);
    const inset = useKeyboardInset();
    const { height: windowHeight } = useWindowDimensions();

    useEffect(() => {
      if (inset === 0) return;
      const focused = TextInput.State.currentlyFocusedInput();
      if (!focused) return;

      // A frame's grace: the padding below has to be applied before measuring,
      // or the field is measured against a layout that is about to change.
      const timer = setTimeout(() => {
        focused.measureInWindow((_x, y, _width, height) => {
          const visibleBottom = windowHeight - inset - MARGIN;
          const fieldBottom = y + height;
          // Only when it is actually covered. Scrolling a field that is already
          // visible yanks the page for no reason, which reads as a glitch.
          if (fieldBottom <= visibleBottom) return;
          inner.current?.scrollTo({
            y: offset.current + (fieldBottom - visibleBottom),
            animated: true,
          });
        });
      }, 50);
      return () => clearTimeout(timer);
    }, [inset, windowHeight]);

    return (
      <ScrollView
        ref={(node) => {
          inner.current = node;
          if (typeof ref === "function") ref(node);
          else if (ref) ref.current = node;
        }}
        // Without this the first tap with the keyboard up is eaten dismissing
        // it, so a Save button appears to do nothing until tapped twice.
        keyboardShouldPersistTaps="handled"
        scrollEventThrottle={16}
        onScroll={(event: NativeSyntheticEvent<NativeScrollEvent>) => {
          offset.current = event.nativeEvent.contentOffset.y;
          onScroll?.(event);
        }}
        // Only while the keyboard is up. Unconditional, this was
        // `paddingBottom: 0` the rest of the time — last in the array, so it
        // silently erased every screen's gesture-bar padding (`pageEnd`), and
        // the Delete button that padding was added for stayed under the bar.
        contentContainerStyle={[contentContainerStyle, inset > 0 && { paddingBottom: inset }]}
        {...props}
      />
    );
  },
);
