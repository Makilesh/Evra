import { describe, expect, it } from "vitest";
import { dayLabel, formatClock, formatDuration, formatTime, meetingLine } from "@/format";
import { MEETING } from "@/test/fakeApi";

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

describe("formatTime", () => {
  it("shows the 24-hour time", () => {
    expect(formatTime(new Date(2026, 8, 28, 13, 51).getTime())).toBe("13:51");
    expect(formatTime(new Date(2026, 8, 28, 9, 5).getTime())).toBe("09:05");
  });
});

describe("dayLabel", () => {
  const now = new Date(2026, 10, 10, 0, 30).getTime();

  it("says Today and Yesterday across midnight", () => {
    expect(dayLabel(new Date(2026, 10, 10, 0, 10).getTime(), now)).toBe("Today");
    expect(dayLabel(new Date(2026, 10, 9, 23, 50).getTime(), now)).toBe("Yesterday");
  });

  it("gives older days their weekday and date", () => {
    expect(dayLabel(new Date(2026, 10, 3, 9, 30).getTime(), now)).toBe("Tue 3 Nov");
  });
});

describe("meetingLine", () => {
  it("gives the day, the time and the length", () => {
    expect(meetingLine(MEETING)).toMatch(/^Mon 28 Sept? · 13:51 · 12 min$/);
    expect(meetingLine({ ...MEETING, duration_ms: null })).toMatch(/^Mon 28 Sept? · 13:51$/);
  });
});
