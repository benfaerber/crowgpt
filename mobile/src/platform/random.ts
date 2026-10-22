import { getRandomBytes } from "expo-crypto";

import type { RandomBytes } from "../domain/ids";

/** The device's random source. Kept in its own module so nothing pure imports a native one. */
export const deviceRandomBytes: RandomBytes = (length) => getRandomBytes(length);
