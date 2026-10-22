import { describe, expect, it } from "vitest";

import {
  BUILTIN,
  rememberMics,
  reorder,
  resolveMic,
  seedFromPin,
  usingFirstChoice,
  type KnownMic,
} from "../../src/domain/micPriority";
import type { AudioInputDescription } from "../../src/recording/Recorder";

/**
 * The case this exists for: buy a good microphone, set it first, then one
 * morning walk out without it. A single pin falls back silently to something
 * nobody chose; a list says what should happen instead.
 */
const usb = (name = "VideoMic Me-C"): AudioInputDescription => ({
  preference: "type:22",
  type: 22,
  typeLabel: "USB_HEADSET",
  name,
  isBuiltIn: false,
  isExternal: true,
});

const phone: AudioInputDescription = {
  preference: "builtin",
  type: 15,
  typeLabel: "BUILTIN_MIC",
  name: "Pixel",
  isBuiltIn: true,
  isExternal: false,
};

const NOW = "2026-07-26T14:00:00Z";

describe("remembering microphones", () => {
  it("keeps one that is not plugged in", () => {
    // The whole point. A list you can only arrange while the hardware is
    // attached is one you cannot arrange on the walk out of the door.
    const known = rememberMics([], [phone, usb()], NOW);
    const later = rememberMics(known, [phone], NOW);
    expect(later.map((m) => m.preference)).toContain("type:22");
  });

  it("always has the phone microphone", () => {
    expect(rememberMics([], [], NOW).map((m) => m.preference)).toEqual(["builtin"]);
  });

  it("appends a new microphone rather than promoting it", () => {
    // Plugging something in must not silently change what the next recording
    // runs through — that is the behaviour this replaces.
    const known: KnownMic[] = [{ ...BUILTIN }];
    const after = rememberMics(known, [phone, usb()], NOW);
    expect(after.map((m) => m.preference)).toEqual(["builtin", "type:22"]);
  });

  it("does not list the same microphone twice when it comes back", () => {
    const first = rememberMics([], [phone, usb()], NOW);
    const second = rememberMics(first, [phone, usb()], NOW);
    expect(second.filter((m) => m.preference === "type:22")).toHaveLength(1);
  });

  it("adopts a changed name instead of adding a duplicate", () => {
    const first = rememberMics([], [usb("VideoMic Me-C")], NOW);
    const second = rememberMics(first, [usb("RODE VideoMic")], NOW);
    expect(second.filter((m) => m.preference === "type:22")).toHaveLength(1);
    expect(second.find((m) => m.preference === "type:22")?.label).toBe("RODE VideoMic");
  });
});

describe("resolving which microphone to use", () => {
  const priority: KnownMic[] = [
    { preference: "type:22", label: "VideoMic Me-C" },
    { ...BUILTIN },
  ];

  it("uses the first choice when it is attached", () => {
    expect(resolveMic(priority, [phone, usb()])).toBe("type:22");
  });

  it("falls through to the phone when it is not", () => {
    // The morning you forget the mic. It records, through something known.
    expect(resolveMic(priority, [phone])).toBe("builtin");
  });

  it("never falls through to auto by accident", () => {
    // "auto" is what routes a capture through earbuds. Reaching it should only
    // happen because somebody put it in the list.
    expect(resolveMic([], [phone])).toBe("builtin");
  });

  it("honours auto when it was deliberately chosen", () => {
    expect(resolveMic([{ preference: "auto", label: "Whatever is connected" }], [phone]))
      .toBe("auto");
  });

  it("skips a missing first choice and takes the second", () => {
    const three: KnownMic[] = [
      { preference: "type:11", label: "Some other USB mic" },
      { preference: "type:22", label: "VideoMic Me-C" },
      { ...BUILTIN },
    ];
    expect(resolveMic(three, [phone, usb()])).toBe("type:22");
  });
});

describe("saying so when the first choice is missing", () => {
  const priority: KnownMic[] = [
    { preference: "type:22", label: "VideoMic Me-C" },
    { ...BUILTIN },
  ];

  it("is quiet when the first choice is in use", () => {
    expect(usingFirstChoice(priority, [phone, usb()])).toBe(true);
  });

  it("reports a fall-through", () => {
    expect(usingFirstChoice(priority, [phone])).toBe(false);
  });

  it("treats an empty list as nothing to warn about", () => {
    expect(usingFirstChoice([], [phone])).toBe(true);
  });
});

describe("arranging the list", () => {
  const mics: KnownMic[] = [
    { preference: "builtin", label: "Phone" },
    { preference: "type:22", label: "VideoMic Me-C" },
  ];

  it("moves an entry up", () => {
    expect(reorder(mics, 1, 0).map((m) => m.preference)).toEqual(["type:22", "builtin"]);
  });

  it("leaves the list alone for a no-op move", () => {
    expect(reorder(mics, 0, 0)).toEqual(mics);
  });

  it("ignores an out-of-range move rather than dropping an entry", () => {
    expect(reorder(mics, 0, 5)).toHaveLength(2);
    expect(reorder(mics, -1, 0)).toHaveLength(2);
  });
});

describe("carrying over the old single pin", () => {
  it("names the phone microphone properly rather than 'Current choice'", () => {
    // The bug this fixes: the list opened saying "Current choice — in use now",
    // which is the one thing a microphone row must not leave you guessing about.
    const seeded = rememberMics(seedFromPin("builtin", [phone]), [phone], NOW);
    expect(seeded.map((m) => m.label)).toEqual(["Phone microphone"]);
  });

  it("names a pinned external mic after the hardware", () => {
    const seeded = rememberMics(seedFromPin("type:22", [phone, usb()]), [phone, usb()], NOW);
    expect(seeded[0].label).toBe("VideoMic Me-C");
  });

  it("still names one that is not plugged in when the list is built", () => {
    // Carried over on a morning the mic is at home. It has to say something,
    // and "Previously chosen microphone" beats a raw "type:22".
    const seeded = seedFromPin("type:22", [phone]);
    expect(seeded[0].label).toBe("Previously chosen microphone");
  });

  it("keeps an explicit auto rather than silently dropping it", () => {
    const seeded = rememberMics(seedFromPin("auto", [phone]), [phone], NOW);
    expect(seeded.map((m) => m.preference)).toEqual(["auto", "builtin"]);
  });

  it("does not list the phone microphone twice", () => {
    const seeded = rememberMics(seedFromPin("builtin", [phone]), [phone], NOW);
    expect(seeded.filter((m) => m.preference === "builtin")).toHaveLength(1);
  });
});

describe("repairing a stored list", () => {
  it("corrects a label this app owns, however it got saved", () => {
    // The one that bit: a placeholder shipped, was written to settings, and
    // then could not be dislodged — the path that produced it never ran again,
    // and reinstalling changed nothing because settings survive a reinstall.
    const stored: KnownMic[] = [{ preference: "builtin", label: "Current choice" }];
    expect(rememberMics(stored, [phone], NOW)[0].label).toBe("Phone microphone");
  });

  it("corrects a stored auto label too", () => {
    const stored: KnownMic[] = [{ preference: "auto", label: "Current choice" }];
    expect(rememberMics(stored, [phone], NOW)[0].label).toBe("Whatever Android picks");
  });

  it("leaves a real hardware name alone", () => {
    // Only the two this app names are ours to overwrite. A microphone's own
    // product name is the best label there is.
    const stored: KnownMic[] = [{ preference: "type:22", label: "VideoMic Me-C" }];
    expect(rememberMics(stored, [phone], NOW)[0].label).toBe("VideoMic Me-C");
  });

  it("does not disturb the order while repairing", () => {
    const stored: KnownMic[] = [
      { preference: "type:22", label: "VideoMic Me-C" },
      { preference: "builtin", label: "Current choice" },
    ];
    expect(rememberMics(stored, [phone], NOW).map((m) => m.preference))
      .toEqual(["type:22", "builtin"]);
  });
});

describe("virtual inputs", () => {
  const submix: KnownMic = { preference: "type:25", label: "type 25" };
  const echo: KnownMic = { preference: "type:28", label: "type 28" };

  it("drops ones a phone saved before they were filtered out", () => {
    // A Pixel lists REMOTE_SUBMIX and ECHO_REFERENCE among its inputs. Both got
    // offered as microphones, and a phone that saw them once has them stored.
    const stored: KnownMic[] = [submix, echo, { preference: "builtin", label: "Phone" }];
    expect(rememberMics(stored, [phone], NOW).map((m) => m.preference)).toEqual(["builtin"]);
  });

  it("keeps a real microphone sitting between them", () => {
    const stored: KnownMic[] = [
      submix,
      { preference: "type:22", label: "VideoMic Me-C" },
      echo,
    ];
    expect(rememberMics(stored, [phone], NOW).map((m) => m.preference))
      .toEqual(["type:22", "builtin"]);
  });

  it("still resolves to something recordable if one was first choice", () => {
    // Recording through ECHO_REFERENCE captures the phone's own playback, so
    // falling through to the built-in mic is the only safe answer.
    const repaired = rememberMics([echo], [phone], NOW);
    expect(resolveMic(repaired, [phone])).toBe("builtin");
  });
});
