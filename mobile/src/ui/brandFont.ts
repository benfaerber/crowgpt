import { useFonts } from "expo-font";
import type { TextStyle } from "react-native";

/**
 * The promo site's wordmark face, for the titles that ARE the brand —
 * CrowGPT on the home screen, CawScout on the map. Playpen Sans at the
 * promo's exact weight (a static 600 instance; Android takes the variable
 * file's default axis otherwise and renders it thin).
 *
 * Returns undefined until loaded so the system face shows in the meantime —
 * an unknown fontFamily on Android falls back silently in release but
 * screams in dev.
 */
export function useBrandTitleFont(): TextStyle | undefined {
  const [loaded] = useFonts({
    "PlaypenSans-SemiBold": require("../../assets/fonts/PlaypenSans-SemiBold.ttf"),
  });
  // fontWeight stays normal: the weight is baked into the instance, and
  // asking Android for bold on top makes it synthesize a fake one.
  return loaded
    ? { fontFamily: "PlaypenSans-SemiBold", fontWeight: "normal" }
    : undefined;
}
