// Times and dates as the window shows them.
import type { MeetingSummary } from "@/bridge";
import { strings } from "@/strings";

const DAY_MS = 86_400_000;

export function formatClock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const seconds = String(total % 60).padStart(2, "0");
  return hours > 0 ? `${hours}:${minutes}:${seconds}` : `${minutes}:${seconds}`;
}

export function formatDuration(ms: number | null): string {
  if (ms === null) return "";
  const minutes = Math.round(ms / 60_000);
  return minutes < 1 ? "<1 min" : `${minutes} min`;
}

export function formatTime(epochMs: number): string {
  return new Date(epochMs).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function formatDay(epochMs: number): string {
  return new Date(epochMs).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
}

function startOfDay(epochMs: number): number {
  const day = new Date(epochMs);
  day.setHours(0, 0, 0, 0);
  return day.getTime();
}

/** The heading a meeting is listed under: Today, Yesterday, or its date ("Tue 3 Nov"). */
export function dayLabel(epochMs: number, now: number): string {
  const days = Math.round((startOfDay(now) - startOfDay(epochMs)) / DAY_MS);
  if (days === 0) return strings.today;
  if (days === 1) return strings.yesterday;
  return formatDay(epochMs);
}

/** "Mon 28 Sept · 13:51 · 12 min" */
export function meetingLine(meeting: MeetingSummary): string {
  return [formatDay(meeting.started_at), formatTime(meeting.started_at), formatDuration(meeting.duration_ms)]
    .filter(Boolean)
    .join(" · ");
}
