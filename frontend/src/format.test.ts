import { describe, expect, it } from "vitest";
import { formatClock, formatDate, formatDuration } from "@/format";

describe("formatClock", () => {
  it("shows minutes and seconds, and hours only when needed", () => {
    expect(formatClock(0)).toBe("00:00");
    expect(formatClock(65_000)).toBe("01:05");
    expect(formatClock(3_725_000)).toBe("1:02:05");
    expect(formatClock(-5)).toBe("00:00");
  });
});

describe("formatDuration", () => {
  it("rounds to minutes", () => {
    expect(formatDuration(720_000)).toBe("12 min");
    expect(formatDuration(20_000)).toBe("<1 min");
    expect(formatDuration(null)).toBe("");
  });
});

describe("formatDate", () => {
  it("shows the day, month and time", () => {
    const text = formatDate(new Date(2026, 8, 28, 13, 51).getTime());
    expect(text).toMatch(/28/);
    expect(text).toMatch(/Sep/);
    expect(text).toMatch(/13:51/);
  });
});
