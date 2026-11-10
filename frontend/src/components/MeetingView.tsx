import { useEffect, useState } from "react";
import type { MeetingDetail } from "@/bridge";
import { copyText } from "@/clipboard";
import { CheckIcon, CopyIcon, PencilIcon } from "@/components/icons";
import { NoteView } from "@/components/NoteView";
import { Stamp } from "@/components/Stamp";
import { TranscriptView } from "@/components/TranscriptView";
import { meetingLine } from "@/format";
import { noteToMarkdown, pointCount } from "@/note";
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
  const { meeting, note, utterances } = detail;
  const line = [meetingLine(meeting), strings.oneOnOne].join(" · ");
  const settled = note !== null && !stage;

  function cite(utteranceId: string) {
    setHighlight(utteranceId);
    setTab("transcript");
  }

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 px-[var(--gutter)] pt-[30px]">
        <header className="flex flex-wrap items-start justify-between gap-x-8 gap-y-4">
          <div className="min-w-0 flex-[1_1_20rem]">
            <Title title={meeting.title} onRename={onRename} />
            <p className="mt-2 text-[13px] leading-5 text-muted tabular-nums">{line}</p>
            {hints && hints.length > 0 && (
              <ul aria-label={strings.captureNotes} className="mt-2 space-y-0.5 text-[13px] leading-5 text-muted">
                {hints.map((hint) => (
                  <li key={hint}>{hint}</li>
                ))}
              </ul>
            )}
          </div>
          {settled && <Stamp model={note.model} points={pointCount(note)} />}
        </header>
        <div role="tablist" aria-label={strings.meetingTabs} className="tabs mt-6">
          <button type="button" role="tab" aria-selected={tab === "note"} onClick={() => setTab("note")} className="tab">
            {strings.noteTab}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "transcript"}
            onClick={() => setTab("transcript")}
            className="tab"
          >
            {strings.transcriptTab}
            <span aria-hidden="true" className="ml-1.5 text-[13px] font-medium tabular-nums">
              {strings.lineCount(utterances.length)}
            </span>
          </button>
          <span className="flex-1" />
          {tab === "note" && settled && <CopyButton text={() => noteToMarkdown(meeting.title, line, note)} />}
        </div>
      </div>
      <div role="tabpanel" className="min-h-0 flex-1">
        {tab === "note" ? (
          <NoteView
            note={note}
            utterances={utterances}
            status={noteStatus}
            canWrite={canWrite}
            onWrite={onWrite}
            onCite={cite}
          />
        ) : (
          <TranscriptView utterances={utterances} follow={isLive} highlightId={highlight} />
        )}
      </div>
    </div>
  );
}

function CopyButton({ text }: { text: () => string }) {
  const [result, setResult] = useState<"idle" | "copied" | "failed">("idle");
  useEffect(() => {
    if (result === "idle") return;
    const timer = window.setTimeout(() => setResult("idle"), 2000);
    return () => window.clearTimeout(timer);
  }, [result]);

  async function copy() {
    setResult((await copyText(text())) ? "copied" : "failed");
  }

  return (
    <button
      type="button"
      onClick={() => void copy()}
      className="mb-[9px] inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-band px-3 py-1.5 text-[13px] leading-5 font-semibold transition-colors hover:bg-band-deep"
    >
      {result === "copied" ? <CheckIcon /> : <CopyIcon />}
      <span aria-live="polite">
        {result === "copied" ? strings.copied : result === "failed" ? strings.copyFailed : strings.copyMarkdown}
      </span>
    </button>
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
      <div className="flex items-start gap-2">
        <h1 className="line-clamp-2 min-w-0 font-display text-[clamp(2.25rem,4.6vw,3.75rem)] leading-[0.95] font-extrabold text-balance">
          {title}
        </h1>
        <button
          type="button"
          aria-label={strings.renameMeeting}
          onClick={() => {
            setDraft(title);
            setEditing(true);
          }}
          className="mt-[0.15em] inline-flex size-8 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-band hover:text-ink"
        >
          <PencilIcon />
        </button>
      </div>
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
      className="w-full rounded-lg bg-band px-2 font-display text-[clamp(2.25rem,4.6vw,3.75rem)] leading-[1.1] font-extrabold"
    />
  );
}
