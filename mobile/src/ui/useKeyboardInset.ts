import { useEffect, useState } from "react";
import { Keyboard, Platform } from "react-native";

/**
 * Height of the on-screen keyboard, or 0 when it's down.
 *
 * The app draws edge-to-edge, which stops Android's `adjustResize` from shrinking
 * the window — so a focused field near the bottom of a scroll view sits under the
 * keyboard with no way to scroll it clear. Reading the height directly and adding
 * it as padding gives the content somewhere to go.
 */
export function useKeyboardInset(): number {
  const [inset, setInset] = useState(0);

  useEffect(() => {
    // `will*` fires early enough on iOS to animate with the keyboard; Android
    // only has the `did*` pair.
    const showEvent = Platform.OS === "ios" ? "keyboardWillShow" : "keyboardDidShow";
    const hideEvent = Platform.OS === "ios" ? "keyboardWillHide" : "keyboardDidHide";

    const shown = Keyboard.addListener(showEvent, (event) =>
      setInset(event.endCoordinates?.height ?? 0),
    );
    const hidden = Keyboard.addListener(hideEvent, () => setInset(0));
    return () => {
      shown.remove();
      hidden.remove();
    };
  }, []);

  return inset;
}
