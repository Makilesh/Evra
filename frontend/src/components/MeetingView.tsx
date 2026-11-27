import { type KeyboardEvent, type ReactNode, useEffect, useId, useRef, useState } from "react";
import type { AskRefusal, ItemStatus, MeetingDetail, MeetingSummary, NoteLine, Person } from "@/bridge";
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
import type { WithRefusal } from "@/usePeople";

export const MAX_NAME = 80; // Python's limit on a person's name (store/people.py)

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
  /** Everyone the owner has named, suggested when saying who the 1:1 was with. */
  people: Person[];
  /** Say who the 1:1 was with ("" for no one): null once said, else why not. */
  onSetPerson: (name: string) => Promise<WithRefusal | null>;
  /** A transcript line to open at (a promise's time tab), instead of the meeting's first tab. */
  openAt?: string | null;
  /** Opened from another page: the open tab takes the focus, so the keyboard lands here. */
  focusTab?: boolean;
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
  people,
  onSetPerson,
  openAt = null,
  focusTab = false,
}: MeetingViewProps) {
  const tabs = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (focusTab) tabs.current?.querySelector<HTMLElement>('[aria-selected="true"]')?.focus();
  }, [focusTab]);
  // While live, the owner takes notes; a finished meeting opens on what was written from them,
  // or, from a promise, on the line it came from.
  const [tab, setTab] = useState<Tab>(openAt ? "transcript" : isLive ? "notes" : "note");
  // The tab was reached with the arrow keys: the focus stays on the tab strip.
  const [byKeys, setByKeys] = useState(false);
  const [highlight, setHighlight] = useState<string | null>(openAt);
  const stage = noteStatus?.stage;
  const [seenStage, setSeenStage] = useState(stage);
  if (stage !== seenStage) {
    // a note started being written: show its progress (adjusting state on a prop change); its
    // later stages leave the owner on the tab they chose
    setSeenStage(stage);
    if (stage && !seenStage) setTab("note");
  }
  const { meeting, note, utterances } = detail;
  const person = detail.with ?? null;
  const line = [meetingLine(meeting), person ? strings.withPerson(person.name) : strings.oneOnOne].join(" · ");
  const settled = note !== null && !stage;

  // Arrow keys cycle the tabs, as Windows tab strips do; Tab leaves the strip.
  function onTabKey(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    if ((event.target as HTMLElement).getAttribute("role") !== "tab") return;
    event.preventDefault();
    const step = event.key === "ArrowRight" ? 1 : TABS.length - 1;
    const next = (TABS.indexOf(tab) + step) % TABS.length;
    setByKeys(true);
    setTab(TABS[next]);
    event.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]')[next]?.focus();
  }

  // A tab clicked (or pressed with Enter or Space).
  function choose(next: Tab) {
    setByKeys(false);
    setTab(next);
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
            <DateLine meeting={meeting} person={person} people={people} onSetPerson={onSetPerson} />
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
        <div ref={tabs} role="tablist" aria-label={strings.meetingTabs} onKeyDown={onTabKey} className="tabs mt-6">
          <TabButton selected={tab === "note"} onSelect={() => choose("note")}>
            {strings.noteTab}
          </TabButton>
          <TabButton selected={tab === "transcript"} onSelect={() => choose("transcript")}>
            {strings.transcriptTab}
            <span aria-hidden="true" className="ml-1.5 text-[13px] font-medium tabular-nums">
              {strings.lineCount(utterances.length)}
            </span>
          </TabButton>
          <TabButton selected={tab === "ask"} onSelect={() => choose("ask")}>
            {strings.askTab}
          </TabButton>
          <TabButton selected={tab === "notes"} onSelect={() => choose("notes")}>
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
            focusOnOpen={!byKeys}
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

interface DateLineProps {
  meeting: MeetingSummary;
  person: Person | null;
  people: Person[];
  onSetPerson: (name: string) => Promise<WithRefusal | null>;
}

// The day, time and length, then who the 1:1 was with. The name is a quiet button; it opens an
// input on the band, as the title does, suggesting everyone named so far. Enter saves (an empty
// name says no one), Escape cancels, and either puts the focus back on the button.
function DateLine({ meeting, person, people, onSetPerson }: DateLineProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [refusal, setRefusal] = useState("");
  const button = useRef<HTMLButtonElement>(null);
  const open = useRef(false); // the input, for a reply that lands after it closed
  const saving = useRef(false);
  const refocus = useRef(false);
  const listId = useId();
  const refusalId = useId();

  useEffect(() => {
    if (editing || !refocus.current) return;
    refocus.current = false;
    button.current?.focus();
  }, [editing]);

  function begin() {
    open.current = true;
    setDraft(person?.name ?? "");
    setRefusal("");
    setEditing(true);
  }

  function end(focusButton: boolean) {
    open.current = false;
    refocus.current = focusButton;
    setRefusal("");
    setEditing(false);
  }

  async function save() {
    if (saving.current) return;
    saving.current = true;
    const refused = await onSetPerson(draft.trim());
    saving.current = false;
    if (!open.current) return;
    if (refused === null) end(true);
    else if (refused === "reserved") setRefusal(strings.nameReserved);
  }

  const day = meetingLine(meeting);
  const lead = strings.withPerson(""); // the words before the name
  return (
    <>
      <p className="mt-2 text-[13px] leading-5 text-muted tabular-nums">
        {editing ? (
          <>
            <span>{day}</span>
            {" · "}
            {lead}
            <input
              aria-label={strings.withLabel}
              aria-describedby={refusal ? refusalId : undefined}
              aria-invalid={refusal ? true : undefined}
              autoFocus
              autoComplete="off"
              spellCheck={false}
              list={listId}
              value={draft}
              maxLength={MAX_NAME}
              onChange={(event) => {
                setDraft(event.target.value);
                setRefusal("");
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  // no keypress: it would press the button the focus is about to return to
                  event.preventDefault();
                  void save();
                }
                if (event.key === "Escape") end(true);
              }}
              onBlur={() => {
                if (open.current) end(false);
              }}
              className="ml-0.5 w-56 max-w-full rounded-md bg-band px-1.5 font-semibold text-ink"
            />
            <datalist id={listId}>
              {people.map((p) => (
                <option key={p.id} value={p.name} />
              ))}
            </datalist>
          </>
        ) : (
          <>
            <span>{person ? day : `${day} · ${strings.oneOnOne}`}</span>
            {" · "}
            {person && <span aria-hidden="true">{lead}</span>}
            <button
              ref={button}
              type="button"
              aria-label={person ? strings.withPerson(person.name) : undefined}
              onClick={begin}
              className="ml-0.5 rounded-md font-semibold text-ink underline decoration-rule underline-offset-[3px] hover:decoration-2"
            >
              {person ? person.name : strings.addWith}
            </button>
          </>
        )}
      </p>
      <div aria-live="polite">
        {refusal && (
          <p id={refusalId} className="mt-1 text-[13px] leading-5 text-muted">
            {refusal}
          </p>
        )}
      </div>
    </>
  );
}
