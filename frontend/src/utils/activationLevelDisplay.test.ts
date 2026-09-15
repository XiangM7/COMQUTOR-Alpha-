import { describe, expect, it } from "vitest";
import { formatActivationLevelForDisplay } from "./activationLevelDisplay";

describe("formatActivationLevelForDisplay", () => {
  it("maps dominant to Dominant", () => {
    expect(formatActivationLevelForDisplay("dominant")).toBe("Dominant");
  });

  it("maps regime_level to Dominant", () => {
    expect(formatActivationLevelForDisplay("regime_level")).toBe("Dominant");
  });

  it("maps active to Active", () => {
    expect(formatActivationLevelForDisplay("active")).toBe("Active");
  });

  it("maps capped_active to Active", () => {
    expect(formatActivationLevelForDisplay("capped_active")).toBe("Active");
  });

  it("maps candidate to Emerging", () => {
    expect(formatActivationLevelForDisplay("candidate")).toBe("Emerging");
  });

  it("maps watch to Watchlist", () => {
    expect(formatActivationLevelForDisplay("watch")).toBe("Watchlist");
  });

  it("maps inactive to Inactive", () => {
    expect(formatActivationLevelForDisplay("inactive")).toBe("Inactive");
  });

  it("never returns a raw snake_case token for any known level", () => {
    for (const level of ["dominant", "regime_level", "active", "capped_active", "candidate", "watch", "inactive"]) {
      expect(formatActivationLevelForDisplay(level)).not.toContain("_");
    }
  });

  it("does not crash on an unrecognized future value and humanizes it conservatively", () => {
    expect(formatActivationLevelForDisplay("some_future_state")).toBe("Some Future State");
  });

  it("does not silently misrepresent an unknown value as a known state", () => {
    const result = formatActivationLevelForDisplay("brand_new_level");
    expect(result).not.toBe("Dominant");
    expect(result).not.toBe("Active");
    expect(result).not.toBe("Emerging");
  });

  it("handles null/undefined/empty safely", () => {
    expect(formatActivationLevelForDisplay(null)).toBe("Not available");
    expect(formatActivationLevelForDisplay(undefined)).toBe("Not available");
    expect(formatActivationLevelForDisplay("")).toBe("Not available");
  });

  it("is a pure function with no side effects", () => {
    const input = "dominant";
    const before = { ...({ level: input } as Record<string, string>) };
    formatActivationLevelForDisplay(input);
    expect({ level: input }).toEqual(before);
  });
});
