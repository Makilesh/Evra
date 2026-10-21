import { useState } from "react";
import type { MeetingSummary } from "@/bridge";
import { formatDate, formatDuration } from "@/format";
import { cn } from "@/lib/utils";
import { strings } from "@/strings";

interface MeetingListProps {
  meetings: MeetingSummary[];
  selectedId: string | null;
  liveId: string | null;
  onSelect: (id: string) => void;
}

export function MeetingList({ meetings, selectedId, liveId, onSelect }: MeetingListProps) {
  const [query, setQuery] = useState("");
  const wanted = query.trim().toLowerCase();
  const shown = meetings.filter((m) => m.title.toLowerCase().includes(wanted));
  return (
    <nav aria-label={strings.meetings} className="flex h-full flex-col">
      <input
        type="search"
        aria-label={strings.searchMeetings}
        placeholder={strings.searchMeetings}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        className="m-3 rounded-md border border-line bg-paper px-3 py-1.5 text-sm"
      />
      {meetings.length === 0 ? (
        <p className="px-4 text-sm text-muted-ink">{strings.noMeetings}</p>
      ) : shown.length === 0 ? (
        <p className="px-4 text-sm text-muted-ink">{strings.noMatches}</p>
      ) : (
        <ul className="flex-1 overflow-y-auto">
          {shown.map((meeting) => (
            <li key={meeting.id}>
              <button
                type="button"
                onClick={() => onSelect(meeting.id)}
                aria-current={meeting.id === selectedId ? "true" : undefined}
                className={cn("w-full px-4 py-2 text-left hover:bg-line/60", meeting.id === selectedId && "bg-line")}
              >
                <span className="block truncate">
                  {meeting.id === liveId && <span className="mr-1 text-rec">● {strings.liveNow}</span>}
                  {meeting.title}
                </span>
                <span className="block text-xs text-muted-ink">
                  {[formatDate(meeting.started_at), formatDuration(meeting.duration_ms)].filter(Boolean).join(" · ")}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </nav>
  );
}
