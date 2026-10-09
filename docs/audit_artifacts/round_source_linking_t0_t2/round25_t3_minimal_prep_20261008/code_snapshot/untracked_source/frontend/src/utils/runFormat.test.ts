import { describe, expect, it } from "vitest";
import { describeRunStatus, formatAnalysisDate, formatCreatedAt, pathForRun } from "./runFormat";

describe("describeRunStatus", () => {
  it("gives every run status a text label and a tone", () => {
    expect(describeRunStatus("completed")).toEqual({ label: "Completed", tone: "ok" });
    expect(describeRunStatus("running")).toEqual({ label: "Running", tone: "active" });
    expect(describeRunStatus("queued")).toEqual({ label: "Queued", tone: "neutral" });
    expect(describeRunStatus("partial")).toEqual({ label: "Partial", tone: "warn" });
    expect(describeRunStatus("failed")).toEqual({ label: "Failed", tone: "bad" });
  });

  it("falls back to a neutral, capitalized label for an unknown status", () => {
    expect(describeRunStatus("blocked")).toEqual({ label: "Blocked", tone: "neutral" });
    expect(describeRunStatus("")).toEqual({ label: "Unknown", tone: "neutral" });
  });
});

describe("formatAnalysisDate", () => {
  it("formats a date-only value without any timezone shift", () => {
    expect(formatAnalysisDate("2026-10-06")).toBe("Oct 6, 2026");
    expect(formatAnalysisDate("2026-01-01")).toBe("Jan 1, 2026");
  });

  it("reports a missing date and passes an unrecognized value through", () => {
    expect(formatAnalysisDate(null)).toBe("Not available");
    expect(formatAnalysisDate("last Tuesday")).toBe("last Tuesday");
  });
});

describe("formatCreatedAt", () => {
  it("reports a missing or unparseable timestamp honestly", () => {
    expect(formatCreatedAt(null)).toBe("Not available");
    expect(formatCreatedAt("not a date")).toBe("not a date");
  });

  it("formats a timestamp as a short date and time", () => {
    expect(formatCreatedAt("2026-10-06T14:05:00Z")).toMatch(/^[A-Z][a-z]{2} \d{1,2}, \d{1,2}:\d{2}\s?(AM|PM)$/);
  });
});

describe("pathForRun", () => {
  it("opens completed and partial runs on Research, everything else on Processing", () => {
    expect(pathForRun({ run_id: "r1", status: "completed" })).toBe("/runs/r1/research");
    expect(pathForRun({ run_id: "r1", status: "partial" })).toBe("/runs/r1/research");
    expect(pathForRun({ run_id: "r1", status: "running" })).toBe("/runs/r1/processing");
    expect(pathForRun({ run_id: "r1", status: "queued" })).toBe("/runs/r1/processing");
    expect(pathForRun({ run_id: "r1", status: "failed" })).toBe("/runs/r1/processing");
  });

  it("encodes the run id", () => {
    expect(pathForRun({ run_id: "a/b c", status: "completed" })).toBe("/runs/a%2Fb%20c/research");
  });
});
