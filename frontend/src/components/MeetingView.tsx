import { useState } from "react";
import type { MeetingDetail } from "@/bridge";
import { NoteView } from "@/components/NoteView";
import { TranscriptView } from "@/components/TranscriptView";
import { formatDate, formatDuration } from "@/format";
import { cn } from "@/lib/utils";
import { strings } from "@/strings";
import type { NoteStatus } from "@/useEvra";

interface MeetingViewProps {
  detail: MeetingDetail;
  isLive: boolean;
  noteStatus: NoteStatus | undefined;
  hints: string[] | undefined;
  canWrite: boolean;
  onWrite: () => void;
  onRename: (title: string) => Promise<boolean>;
}

type Tab = "note" | "transcript";

export function MeetingView({ detail, isLive, noteStatus, hints, canWrite, onWrite, onRename }: MeetingViewProps) {
  const [tab, setTab] = useState<Tab>(isLive ? "transcript" : "note");
  const [highlight, setHighlight] = useState<string | null>(null);
  const stage = noteStatus?.stage;
  const [seenStage, setSeenStage] = useState(stage);
  if (stage !== seenStage) {
    // a note started being written: show its progress (adjusting state on a prop change)
    setSeenStage(stage);
    if (stage) setTab("note");
  }
  const { meeting } = detail;

  function cite(utteranceId: string) {
    setHighlight(utteranceId);
    setTab("transcript");
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-line px-6 pt-4">
        <Title title={meeting.title} onRename={onRename} />
        <p className="mt-1 text-xs text-muted-ink">
          {[formatDate(meeting.started_at), formatDuration(meeting.duration_ms), strings.oneOnOne].filter(Boolean).join(" · ")}
        </p>
        {hints && hints.length > 0 && (
          <ul aria-label={strings.captureNotes} className="mt-2 space-y-0.5 text-xs text-muted-ink">
            {hints.map((hint) => (
              <li key={hint}>{hint}</li>
            ))}
          </ul>
        )}
        <div role="tablist" aria-label={strings.meetingTabs} className="mt-3 flex gap-5">
          {(["note", "transcript"] as const).map((name) => (
            <button
              key={name}
              type="button"
              role="tab"
              aria-selected={tab === name}
              onClick={() => setTab(name)}
              className={cn("border-b-2 pb-2 text-sm", tab === name ? "border-accent text-ink" : "border-transparent text-muted-ink")}
            >
              {name === "note" ? strings.noteTab : strings.transcriptTab}
            </button>
          ))}
        </div>
      </div>
      <div role="tabpanel" className="min-h-0 flex-1">
        {tab === "note" ? (
          <NoteView note={detail.note} status={noteStatus} canWrite={canWrite} onWrite={onWrite} onCite={cite} />
        ) : (
          <TranscriptView utterances={detail.utterances} follow={isLive} highlightId={highlight} />
        )}
      </div>
    </div>
  );
}

function Title({ title, onRename }: { title: string; onRename: (title: string) => Promise<boolean> }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);

  async function save() {
    if (await onRename(draft)) setEditing(false);
  }

  if (!editing) {
    return (
      <h2 className="flex items-center gap-2 font-serif text-2xl">
        {title}
        <button
          type="button"
          aria-label={strings.renameMeeting}
          onClick={() => {
            setDraft(title);
            setEditing(true);
          }}
          className="text-base text-muted-ink hover:text-accent"
        >
          ✎
        </button>
      </h2>
    );
  }
  return (
    <input
      aria-label={strings.meetingTitle}
      autoFocus
      value={draft}
      maxLength={200}
      onChange={(event) => setDraft(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === "Enter") void save();
        if (event.key === "Escape") setEditing(false);
      }}
      onBlur={() => setEditing(false)}
      className="w-full rounded-md border border-line bg-paper px-2 py-1 font-serif text-2xl"
    />
  );
}
