import { useEffect, useRef, useState } from "react";
import type { MeetingSummary } from "@/bridge";
import { SearchIcon } from "@/components/icons";
import { dayLabel, formatDuration, formatTime } from "@/format";
import { cn } from "@/lib/utils";
import { strings } from "@/strings";

interface MeetingListProps {
  meetings: MeetingSummary[];
  selectedId: string | null;
  liveId: string | null;
  writingIds?: string[];
  onSelect: (id: string) => void;
  now?: () => number;
}

interface DayGroup {
  label: string;
  meetings: MeetingSummary[];
}

function byDay(meetings: MeetingSummary[], now: number): DayGroup[] {
  const groups = new Map<string, MeetingSummary[]>();
  for (const meeting of meetings) {
    const label = dayLabel(meeting.started_at, now);
    groups.set(label, [...(groups.get(label) ?? []), meeting]);
  }
  return [...groups].map(([label, list]) => ({ label, meetings: list }));
}

// Search (Ctrl K) and the meetings, newest first, under the day they happened.
export function MeetingList({ meetings, selectedId, liveId, writingIds = [], onSelect, now = Date.now }: MeetingListProps) {
  const [query, setQuery] = useState("");
  const search = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "k") {
        event.preventDefault();
        search.current?.focus();
        search.current?.select();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const wanted = query.trim().toLowerCase();
  const shown = meetings.filter((m) => m.title.toLowerCase().includes(wanted));
  const groups = byDay(shown, now());

  return (
    <nav aria-label={strings.meetings} className="flex min-h-0 flex-1 flex-col">
      <div className="relative mx-[18px] mt-3 short:mt-2.5">
        <SearchIcon className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-chip-ink" />
        <input
          ref={search}
          type="search"
          aria-label={strings.searchMeetings}
          placeholder={strings.searchMeetings}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="h-10 w-full rounded-[10px] bg-chip-well pr-16 pl-9 text-ink placeholder:text-chip-ink max-[860px]:pr-3"
        />
        <span
          aria-hidden="true"
          className="kbd pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-chip-ink max-[860px]:hidden"
        >
          {strings.searchShortcut}
        </span>
      </div>
      {meetings.length === 0 ? (
        <p className="px-[18px] pt-4 text-chip-ink">{strings.noMeetings}</p>
      ) : shown.length === 0 ? (
        <p className="px-[18px] pt-4 text-chip-ink">{strings.noMatches}</p>
      ) : (
        <div className="mt-1 min-h-0 flex-1 overflow-y-auto pb-7 pl-3 [mask-image:linear-gradient(to_bottom,black_calc(100%-28px),transparent)]">
          {groups.map((group) => (
            <section key={group.label} aria-label={group.label}>
              <h2 className="caps px-1.5 pt-4 pb-1.5 text-[14px] leading-4 text-chip-ink short:pt-3">{group.label}</h2>
              <ul>
                {group.meetings.map((meeting) => {
                  const selected = meeting.id === selectedId;
                  return (
                    <li key={meeting.id}>
                      <button
                        type="button"
                        onClick={() => onSelect(meeting.id)}
                        aria-current={selected ? "true" : undefined}
                        className={cn(
                          "grid w-full rounded-l-[11px] py-[9px] pr-[18px] pl-1.5 text-left transition-colors",
                          selected ? "bg-pad" : "hover:bg-chip-well",
                        )}
                      >
                        <span className="truncate font-semibold">{meeting.title}</span>
                        <MeetingMeta meeting={meeting} live={meeting.id === liveId} writing={writingIds.includes(meeting.id)} />
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      )}
    </nav>
  );
}

function MeetingMeta({ meeting, live, writing }: { meeting: MeetingSummary; live: boolean; writing: boolean }) {
  if (live) {
    return (
      <span className="flex items-center gap-1.5 text-[13px] leading-[18px] font-semibold">
        <span aria-hidden="true" className="size-2 rounded-full bg-rec" />
        {strings.liveNow}
      </span>
    );
  }
  const when = [formatTime(meeting.started_at), formatDuration(meeting.duration_ms)].filter(Boolean).join(" · ");
  if (writing) {
    // The rail's green block and the pad already say it in words; here a green pip is enough.
    return (
      <span className="flex items-center gap-1.5 text-[13px] leading-[18px] text-chip-ink tabular-nums">
        <span aria-hidden="true" className="size-2 rounded-full bg-rule" />
        <span className="sr-only">{strings.writingNote}</span>
        {when}
      </span>
    );
  }
  return <span className="text-[13px] leading-[18px] text-chip-ink tabular-nums">{when}</span>;
}
