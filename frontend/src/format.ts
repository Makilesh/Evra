// Times and dates as the window shows them.

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

export function formatDate(epochMs: number): string {
  return new Date(epochMs).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}
