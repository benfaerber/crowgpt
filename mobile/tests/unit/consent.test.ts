import { describe, expect, it } from "vitest";

import {
  boldRuns,
  consentBlocksSync,
  describeConsent,
  needsConsent,
  parsePolicy,
} from "../../src/domain/consent";

describe("needsConsent", () => {
  it("asks an account that never accepted any version", () => {
    expect(needsConsent(undefined, 1)).toBe(true);
    expect(needsConsent({}, undefined)).toBe(true);
  });

  it("asks again when the server has a newer version", () => {
    expect(needsConsent({ policyVersion: 1 }, 2)).toBe(true);
  });

  it("lets an accepted account through when the current version is unknown", () => {
    expect(needsConsent({ policyVersion: 1 }, undefined)).toBe(false);
  });

  it("leaves an up-to-date account alone", () => {
    expect(needsConsent({ policyVersion: 2 }, 2)).toBe(false);
  });
});

describe("consentBlocksSync", () => {
  it("blocks until some version is accepted", () => {
    expect(consentBlocksSync(undefined)).toMatch(/policy/);
    expect(consentBlocksSync({ policyVersion: 1 })).toBeUndefined();
  });
});

describe("describeConsent", () => {
  it("says publishing is off unless opted in", () => {
    expect(describeConsent({ policyVersion: 1, allowGenerator: true, allowPublish: false }))
      .toMatch(/never published/);
    expect(describeConsent({ policyVersion: 1, allowGenerator: false, allowPublish: true }))
      .toMatch(/not the generator.*may be published/);
  });
});

describe("parsePolicy", () => {
  it("reads headings, bullets, numbered items and wrapped paragraphs", () => {
    const blocks = parsePolicy(
      "# Title\n\nFirst line\nsecond line.\n\n- one\n  continued\n- two\n\n1. **CawDex**, a thing.\n",
    );
    expect(blocks).toEqual([
      { kind: "heading", level: 1, text: "Title" },
      { kind: "paragraph", text: "First line second line." },
      { kind: "bullet", text: "one continued" },
      { kind: "bullet", text: "two" },
      { kind: "bullet", text: "**CawDex**, a thing.", ordinal: 1 },
    ]);
  });
});

describe("boldRuns", () => {
  it("splits bold from plain and drops single-star emphasis markers", () => {
    expect(boldRuns("only **if you opt in**, and *made* here")).toEqual([
      { text: "only ", bold: false },
      { text: "if you opt in", bold: true },
      { text: ", and made here", bold: false },
    ]);
  });
});
