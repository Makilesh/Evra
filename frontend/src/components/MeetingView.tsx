import { type KeyboardEvent, type ReactNode, useEffect, useState } from "react";
import type { AskRefusal, ItemStatus, MeetingDetail, NoteLine } from "@/bridge";
import { copyText } from "@/clipboard";
import { AskView } from "@/components/AskView";
import { Banner } from "@/components/Banner";
import { CheckIcon, CopyIcon, PencilIcon } from "@/components/icons";
import { NotepadView } from "@/components/NotepadView";
import { NoteView } from "@/components/NoteView";
import { Stamp } from "@/components/Stamp";
import { TranscriptView } from "@/components/TranscriptView";
import { meetingLine } from "@/format";
import { noteToMarkdown, pointCount } from "@/note";
import { lineAt } from "@/notepad";
import { strings } from "@/strings";
import type { NoteStatus } from "@/useEvra";

interface MeetingViewProps {
  detail: MeetingDetail;
  isLive: boolean;
  noteStatus: NoteStatus | undefined;
  hints: string[] | undefined;
  canWrite: boolean;
  /** The owner's typed lines, as the window has them. */
  notes: NoteLine[];
  /** The last save of them failed; they stay in the window until one works. */
  notesFailed: boolean;
  onWrite: () => void;
  onRename: (title: string) => Promise<boolean>;
  onAsk: (text: string) => Promise<AskRefusal | null>;
  onPrepareAsk: () => void;
  onItemStatus: (itemId: string, status: ItemStatus) => void;
  onNotes: (lines: NoteLine[]) => void;
}

type Tab = "note" | "transcript" | "ask" | "notes";

const TABS: Tab[] = ["note", "transcript", "ask", "notes"];

export function MeetingView({
  detail,
  isLive,
  noteStatus,
  hints,
  canWrite,
  notes,
  notesFailed,
  onWrite,
  onRename,
  onAsk,
  onPrepareAsk,
  onItemStatus,
  onNotes,
}: MeetingViewProps) {
  // While live, the owner takes notes; a finished meeting opens on what was written from them.
  const [tab, setTab] = useState<Tab>(isLive ? "notes" : "note");
  const [highlight, setHighlight] = useState<string | null>(null);
  const stage = noteStatus?.stage;
  const [seenStage, setSeenStage] = useState(stage);
  if (stage !== seenStage) {
    // a note started being written: show its progress (adjusting state on a prop change); its
    // later stages leave the owner on the tab they chose
    setSeenStage(stage);
    if (stage && !seenStage) setTab("note");
  }
  const { meeting, note, utterances } = detail;
  const line = [meetingLine(meeting), strings.oneOnOne].join(" · ");
  const settled = note !== null && !stage;

  // Arrow keys cycle the tabs, as Windows tab strips do; Tab leaves the strip.
  function onTabKey(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    if ((event.target as HTMLElement).getAttribute("role") !== "tab") return;
    event.preventDefault();
    const step = event.key === "ArrowRight" ? 1 : TABS.length - 1;
    const next = (TABS.indexOf(tab) + step) % TABS.length;
    setTab(TABS[next]);
    event.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]')[next]?.focus();
  }

  function cite(utteranceId: string) {
    setHighlight(utteranceId);
    setTab("transcript");
  }

  // A typed time opens the transcript on the line being said then.
  function jump(ms: number) {
    setHighlight(lineAt(utterances, ms)?.id ?? null);
    setTab("transcript");
  }

  return (
    <div className="enter flex h-full flex-col">
      <div className="measure-pad shrink-0 px-[var(--gutter)] pt-[30px]">
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
            {/* Above the tabs, so it shows whichever is open: Stop moves to the note's progress. */}
            {notesFailed && (
              <div className="mt-3 max-w-[40rem]">
                <Banner message={strings.notesSaveFailed} />
              </div>
            )}
          </div>
          {settled && <Stamp model={note.model} points={pointCount(note)} />}
        </header>
        <div role="tablist" aria-label={strings.meetingTabs} onKeyDown={onTabKey} className="tabs mt-6">
          <TabButton selected={tab === "note"} onSelect={() => setTab("note")}>
            {strings.noteTab}
          </TabButton>
          <TabButton selected={tab === "transcript"} onSelect={() => setTab("transcript")}>
            {strings.transcriptTab}
            <span aria-hidden="true" className="ml-1.5 text-[13px] font-medium tabular-nums">
              {strings.lineCount(utterances.length)}
            </span>
          </TabButton>
          <TabButton selected={tab === "ask"} onSelect={() => setTab("ask")}>
            {strings.askTab}
          </TabButton>
          <TabButton selected={tab === "notes"} onSelect={() => setTab("notes")}>
            {strings.notesTab}
          </TabButton>
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
            onItemStatus={onItemStatus}
          />
        ) : tab === "transcript" ? (
          <TranscriptView utterances={utterances} follow={isLive} highlightId={highlight} />
        ) : tab === "ask" ? (
          <AskView
            questions={detail.questions}
            utterances={utterances}
            isLive={isLive}
            onAsk={onAsk}
            onPrepare={onPrepareAsk}
            onCite={cite}
          />
        ) : (
          <NotepadView
            lines={notes}
            meeting={meeting}
            utterances={utterances}
            isLive={isLive}
            noted={note !== null}
            onChange={onNotes}
            onJump={jump}
          />
        )}
      </div>
    </div>
  );
}

// Only the selected tab is in the Tab order; the arrow keys reach the others.
function TabButton({ selected, onSelect, children }: { selected: boolean; onSelect: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={selected}
      tabIndex={selected ? 0 : -1}
      onClick={onSelect}
      className="tab"
    >
      {children}
    </button>
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

// Dates and times never break at a hyphen or colon: "Recording 2026-11-10 18:09" wraps
// between words, never as "Recording 2026-" over "11-10 18:09".
function keepNumbersWhole(text: string): ReactNode[] {
  return text.split(/(\d+(?:[-:./]\d+)+)/).map((part, index) =>
    index % 2 === 1 ? (
      <span key={index} className="whitespace-nowrap">
        {part}
      </span>
    ) : (
      part
    ),
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
          {keepNumbersWhole(title)}
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
