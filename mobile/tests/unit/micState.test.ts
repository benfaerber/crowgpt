import { describe, expect, it } from "vitest";

import { micState, shouldReopenSession } from "../../src/domain/micState";
import { BUILTIN, type KnownMic } from "../../src/domain/micPriority";
import type { ActiveSessionInput, AudioInputDescription } from "../../src/recording/Recorder";

const RODE: KnownMic = {
  preference: "type:22",
  label: "VideoMic Me-C",
  typeLabel: "USB_HEADSET",
};

function attachedRode(): AudioInputDescription {
  return {
    preference: "type:22",
    type: 22,
    typeLabel: "USB_HEADSET",
    name: "VideoMic Me-C",
    isBuiltIn: false,
    isExternal: true,
  };
}

function attachedBuiltin(): AudioInputDescription {
  return {
    preference: "builtin",
    type: 15,
    typeLabel: "BUILTIN_MIC",
    name: "Phone microphone",
    isBuiltIn: true,
    isExternal: false,
  };
}

function session(over: Partial<ActiveSessionInput> = {}): ActiveSessionInput {
  return {
    requested: "builtin",
    routed: "builtin",
    routedLabel: "BUILTIN_MIC",
    honoured: true,
    recording: false,
    ...over,
  };
}

describe("micState with nothing open", () => {
  it("names what the next recording would use", () => {
    const state = micState({
      priority: [RODE, BUILTIN],
      attached: [attachedBuiltin(), attachedRode()],
      session: null,
    });
    expect(state.preference).toBe("type:22");
    expect(state.label).toBe("VideoMic Me-C");
    expect(state.live).toBe(false);
    expect(state.warning).toBeUndefined();
  });

  it("warns when the first choice is absent", () => {
    const state = micState({
      priority: [RODE, BUILTIN],
      attached: [attachedBuiltin()],
      session: null,
    });
    expect(state.preference).toBe("builtin");
    expect(state.warning).toContain("VideoMic Me-C isn't connected");
  });

  it("says nothing about a list nobody has arranged", () => {
    const state = micState({ priority: [], attached: [attachedBuiltin()], session: null });
    expect(state.preference).toBe("builtin");
    expect(state.label).toBe(BUILTIN.label);
    expect(state.warning).toBeUndefined();
  });
});

describe("micState with a session open", () => {
  it("reports the session's route, not the list's answer", () => {
    const state = micState({
      priority: [RODE, BUILTIN],
      attached: [attachedBuiltin(), attachedRode()],
      session: session({ requested: "builtin", routed: "builtin" }),
    });
    expect(state.preference).toBe("builtin");
    expect(state.live).toBe(true);
  });

  /**
   * Capture 107. The buffer opened on the phone mic, the Rode was plugged in
   * afterwards, and every prediction switched to it while the open session did
   * not — so the caption named the Rode and the warning went white.
   */
  it("warns when a mic arrived after the session opened", () => {
    const state = micState({
      priority: [RODE, BUILTIN],
      attached: [attachedBuiltin(), attachedRode()],
      session: session({ requested: "builtin", routed: "builtin" }),
    });
    expect(state.warning).toContain("Recording on Phone microphone");
    expect(state.warning).toContain("VideoMic Me-C");
    expect(state.warning).toContain("cannot change microphone");
  });

  it("stays quiet when the session and the list agree", () => {
    const state = micState({
      priority: [RODE, BUILTIN],
      attached: [attachedBuiltin(), attachedRode()],
      session: session({ requested: "type:22", routed: "type:22" }),
    });
    expect(state.preference).toBe("type:22");
    expect(state.label).toBe("VideoMic Me-C");
    expect(state.warning).toBeUndefined();
  });

  it("does not accuse anything before the policy has chosen a route", () => {
    const state = micState({
      priority: [RODE, BUILTIN],
      attached: [attachedBuiltin(), attachedRode()],
      session: session({ requested: "builtin", routed: null, routedLabel: null }),
    });
    expect(state.preference).toBe("builtin");
    expect(state.live).toBe(true);
    expect(state.warning).toBeUndefined();
  });

  it("reports a refused pin", () => {
    const state = micState({
      priority: [BUILTIN],
      attached: [attachedBuiltin()],
      session: session({ requested: "type:22", routed: "builtin", honoured: false }),
    });
    expect(state.warning).toContain("Asked for");
    expect(state.warning).toContain("Phone microphone");
  });

  it("still reports a fall-through the session agrees with", () => {
    const state = micState({
      priority: [RODE, BUILTIN],
      attached: [attachedBuiltin()],
      session: session({ requested: "builtin", routed: "builtin" }),
    });
    expect(state.warning).toContain("VideoMic Me-C isn't connected");
  });
});

describe("shouldReopenSession", () => {
  it("reopens onto a microphone plugged in after the buffer started", () => {
    expect(shouldReopenSession(session({ routed: "builtin" }), "type:22")).toBe(true);
  });

  it("reopens back onto the phone when the good mic is pulled out", () => {
    expect(shouldReopenSession(session({ routed: "type:22" }), "builtin")).toBe(true);
  });

  it("leaves a session that is already on the right microphone", () => {
    expect(shouldReopenSession(session({ routed: "type:22" }), "type:22")).toBe(false);
  });

  it("never interrupts a capture", () => {
    expect(
      shouldReopenSession(session({ routed: "builtin", recording: true }), "type:22"),
    ).toBe(false);
  });

  it("waits for the policy to choose a route before judging it", () => {
    expect(
      shouldReopenSession(session({ requested: "builtin", routed: null }), "type:22"),
    ).toBe(false);
  });

  it("does nothing when no session is open", () => {
    expect(shouldReopenSession(null, "type:22")).toBe(false);
  });

  /**
   * From Ben's synced log, 2026-07-31: "reopened the buffer on a new
   * microphone {from: type:15, to: builtin}", four times in ninety seconds.
   * Those are one device under two names — enumeration says `type:15`, the
   * preference list says `builtin` — so the check decided the microphone had
   * changed on every input event and restarted the session, discarding the
   * pre-roll ring each time. A capture that should have reached back fifteen
   * seconds reached back three.
   */
  it("does not mistake the phone mic's two names for two microphones", () => {
    expect(shouldReopenSession(session({ routed: "type:15" }), "builtin")).toBe(false);
    expect(shouldReopenSession(session({ routed: "builtin" }), "type:15")).toBe(false);
  });

  it("still adopts a real change when the phone mic is one side of it", () => {
    expect(shouldReopenSession(session({ routed: "type:15" }), "type:22")).toBe(true);
    expect(shouldReopenSession(session({ routed: "type:22" }), "builtin")).toBe(true);
  });
});
