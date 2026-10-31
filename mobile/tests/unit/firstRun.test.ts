import { describe, expect, it } from "vitest";

import { asksForEnrollment, enrollmentProblem } from "../../src/domain/firstRun";

describe("asksForEnrollment", () => {
  it("asks an unenrolled phone", () => {
    expect(asksForEnrollment(false, false)).toBe(true);
  });

  it("leaves an enrolled phone alone", () => {
    expect(asksForEnrollment(true, false)).toBe(false);
  });

  it("stops asking for the rest of the launch once skipped", () => {
    expect(asksForEnrollment(false, true)).toBe(false);
  });
});

describe("enrollmentProblem", () => {
  it("refuses an empty token, since the server would too", () => {
    expect(enrollmentProblem("")).toMatch(/token/);
    expect(enrollmentProblem("   ")).toMatch(/token/);
  });

  it("accepts anything else — the server decides whether it is right", () => {
    expect(enrollmentProblem("ddMnrh")).toBeUndefined();
  });
});
