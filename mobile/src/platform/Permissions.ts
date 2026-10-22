import { Linking, PermissionsAndroid, Platform } from "react-native";
import * as Camera from "expo-camera";
import * as Location from "expo-location";

/** Not in RN's PERMISSIONS map on every version, and it is a plain string anyway. */
const NOTIFICATION_PERMISSION = "android.permission.POST_NOTIFICATIONS" as never;

export type PermissionState =
  /** Held. The feature works. */
  | "granted"
  /** Never asked, or asked and dismissed. Asking again will show the dialog. */
  | "undetermined"
  /** Refused, but the OS will still show the dialog if we ask again. */
  | "denied"
  /** Refused hard. Only the system settings screen can turn it back on. */
  | "blocked";

export type PermissionKey = "microphone" | "location" | "camera" | "notifications";

export interface PermissionInfo {
  key: PermissionKey;
  title: string;
  /** What breaks without it — shown to the user, so it is about consequence, not API names. */
  why: string;
  /** Whether the app is unusable without it. */
  essential: boolean;
  state: PermissionState;
}

export interface PermissionsManager {
  list(): Promise<PermissionInfo[]>;
  request(key: PermissionKey): Promise<PermissionInfo>;
  /** Deep-link to the OS settings page — the only route back from `blocked`. */
  openSystemSettings(): Promise<void>;
}

const DESCRIPTIONS: Record<PermissionKey, Omit<PermissionInfo, "state">> = {
  microphone: {
    key: "microphone",
    title: "Microphone",
    why: "Required. Without it nothing can be recorded.",
    essential: true,
  },
  camera: {
    key: "camera",
    title: "Camera",
    why: "Only needed to film a capture. Audio-only recording works without it.",
    essential: false,
  },
  notifications: {
    key: "notifications",
    title: "Notifications",
    why:
      "Only needed to listen with the screen off. Android requires a visible "
      + "notification while the microphone is held, and without this permission "
      + "the mic can be open with nothing on screen to say so.",
    essential: false,
  },
  location: {
    key: "location",
    title: "Location",
    why: "Tags each capture with where it was made. Recording still works without it, but captures won't be placed on a map.",
    essential: false,
  },
};

export class DevicePermissions implements PermissionsManager {
  /**
   * Android's `check()` only answers yes/no — it cannot tell "never asked" from
   * "refused". Once we have asked in this session the result does distinguish
   * them, so remember it rather than reporting a refusal as though the dialog
   * had never been shown.
   */
  private asked = new Map<PermissionKey, PermissionState>();

  async list(): Promise<PermissionInfo[]> {
    return Promise.all(
      (Object.keys(DESCRIPTIONS) as PermissionKey[]).map(async (key) => ({
        ...DESCRIPTIONS[key],
        state: await this.stateOf(key),
      })),
    );
  }

  async request(key: PermissionKey): Promise<PermissionInfo> {
    const state =
      key === "microphone"
        ? await this.requestMic()
        : key === "camera"
          ? await this.requestCamera()
          : key === "notifications"
            ? await this.requestNotifications()
            : await this.requestLocation();
    this.asked.set(key, state);
    return { ...DESCRIPTIONS[key], state };
  }

  async openSystemSettings(): Promise<void> {
    await Linking.openSettings();
  }

  private async stateOf(key: PermissionKey): Promise<PermissionState> {
    if (key === "camera") {
      const current = await Camera.Camera.getCameraPermissionsAsync();
      if (current.granted) return "granted";
      if (current.status === "undetermined") return "undetermined";
      return current.canAskAgain ? "denied" : "blocked";
    }
    if (key === "location") {
      const current = await Location.getForegroundPermissionsAsync();
      if (current.granted) return "granted";
      if (current.status === "undetermined") return "undetermined";
      return current.canAskAgain ? "denied" : "blocked";
    }

    if (Platform.OS !== "android") return "granted";
    if (key === "notifications") {
      // Only a runtime permission from Android 13. Below that it is held by
      // being declared, and reporting it as anything else would put a button on
      // the screen that cannot do anything.
      if ((Platform.Version as number) < 33) return "granted";
      const held = await PermissionsAndroid.check(NOTIFICATION_PERMISSION);
      if (held) return "granted";
      return this.asked.get(key) ?? "undetermined";
    }
    const held = await PermissionsAndroid.check(
      PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
    );
    if (held) return "granted";
    return this.asked.get(key) ?? "undetermined";
  }

  /**
   * The one that makes background listening honest.
   *
   * Declared in the manifest since the foreground service arrived, and never
   * asked for — so on any phone since Android 13 the service ran with its
   * notification suppressed. The microphone was held from a pocket with nothing
   * on screen to say so, which is the exact situation the notification exists
   * to prevent.
   */
  private async requestNotifications(): Promise<PermissionState> {
    if (Platform.OS !== "android") return "granted";
    if ((Platform.Version as number) < 33) return "granted";
    const result = await PermissionsAndroid.request(NOTIFICATION_PERMISSION);
    if (result === PermissionsAndroid.RESULTS.GRANTED) return "granted";
    if (result === PermissionsAndroid.RESULTS.NEVER_ASK_AGAIN) return "blocked";
    return "denied";
  }

  private async requestMic(): Promise<PermissionState> {
    if (Platform.OS !== "android") return "granted";
    const result = await PermissionsAndroid.request(
      PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
    );
    if (result === PermissionsAndroid.RESULTS.GRANTED) return "granted";
    if (result === PermissionsAndroid.RESULTS.NEVER_ASK_AGAIN) return "blocked";
    return "denied";
  }

  private async requestCamera(): Promise<PermissionState> {
    const result = await Camera.Camera.requestCameraPermissionsAsync();
    if (result.granted) return "granted";
    return result.canAskAgain ? "denied" : "blocked";
  }

  private async requestLocation(): Promise<PermissionState> {
    const result = await Location.requestForegroundPermissionsAsync();
    if (result.granted) return "granted";
    return result.canAskAgain ? "denied" : "blocked";
  }
}
