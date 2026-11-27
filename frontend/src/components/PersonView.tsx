import { useEffect, useId, useRef, useState, type ReactNode, type Ref } from "react";
import type { ItemStatus, NoteBlock, Person, PersonPage } from "@/bridge";
import { PencilIcon } from "@/components/icons";
import { MAX_NAME } from "@/components/MeetingView";
import { GroupHead, MeetingLink, PromiseSections, SectionHead as Head } from "@/components/PromiseSections";
import { dayLabel, formatClock, meetingLine } from "@/format";
import { useFocusOnLanding } from "@/landing";
import { briefFailureText, strings } from "@/strings";
import { promisesOf, type RenameRefusal, type ShownPromises } from "@/usePeople";
import type { BriefStatus } from "@/usePersonPage";

interface PersonViewProps {
  /** From the people list, so the name shows before Python has read the page. */
  person: Person;
  /** The page as Python read it; null while it is read. */
  page: PersonPage | null;
  /** The window's one list of promises (RC7); null until Python has listed them. */
  promises: ShownPromises | null;
  promisesUnread: boolean;
  /** How their last brief asked for went, when it hasn't landed. */
  brief: BriefStatus | undefined;
  onStatus: (id: string, status: ItemStatus) => void;
  /** Open a meeting; at a transcript line, when given. */
  onOpenMeeting: (meetingId: string, utteranceId?: string) => void;
  onWriteBrief: () => void;
  /** Null once renamed, else why not. */
  onRename: (name: string) => Promise<RenameRefusal | null>;
  /** True once forgotten. */
  onForget: () => Promise<boolean>;
  now?: () => number;
}

// A person's page, to prepare the next 1:1 with them: their name (renamed in place), the open
// promises both ways as the Promises page shows them, what was left for next time and the
// questions still open from their last 1:1, the brief, their 1:1s, and Forget this person (D14).
// On the note's sheet, in its own scroller (#root clips).
export function PersonView(props: PersonViewProps) {
  const { person, page, promises, promisesUnread, onOpenMeeting, now = Date.now } = props;
  const ids = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  useFocusOnLanding(heading);
  const name = page?.person.name ?? person.name;
  const theirs = promises && promisesOf(promises, person.id);
  const promised = theirs !== null && theirs.you.length + theirs.them.length > 0;
  const unread = promises === null && promisesUnread;
  const last = page?.last ?? null;
  const day = (epochMs: number) => dayLabel(epochMs, now());
  return (
    <div className="enter h-full overflow-y-auto">
      <div className="measure-pad px-[var(--gutter)] pt-[30px] pb-12">
        <NameTitle ref={heading} name={name} onRename={props.onRename} />
        <div className="sheet measure -mx-2.5 mt-4">
          {/* always there, so a promise leaving with the focus hands it on (PromiseSections) */}
          <section aria-labelledby={promised || unread ? `${ids}-promises` : undefined}>
            {(promised || unread) && <Head id={`${ids}-promises`}>{strings.openPromises}</Head>}
            {unread && <Muted>{strings.promisesUnread}</Muted>}
            {theirs && (
              <PromiseSections
                promises={theirs}
                onStatus={props.onStatus}
                onOpenMeeting={onOpenMeeting}
                fallback={heading}
                level={3}
                now={now}
              />
            )}
          </section>
          {last && last.next_time.length + last.open_questions.length > 0 && (
            <section aria-labelledby={`${ids}-last`}>
              <Head id={`${ids}-last`}>{strings.fromLastTime}</Head>
              {[
                { key: "next", title: strings.forNextTime, blocks: last.next_time },
                { key: "open", title: strings.openQuestions, blocks: last.open_questions },
              ]
                .filter((group) => group.blocks.length > 0)
                .map((group) => (
                  <Group key={group.key} id={`${ids}-${group.key}`} title={group.title}>
                    {group.blocks.map((block, index) => (
                      <LastRow
                        key={index}
                        block={block}
                        where={`${last.title} · ${day(last.started_at)}`}
                        onOpen={(utteranceId) => onOpenMeeting(last.meeting_id, utteranceId)}
                      />
                    ))}
                  </Group>
                ))}
            </section>
          )}
          {page && (
            <section aria-labelledby={`${ids}-brief`}>
              <Head id={`${ids}-brief`}>{strings.catchMeUp}</Head>
              <CatchMeUp page={page} status={props.brief} onWrite={props.onWriteBrief} onOpen={onOpenMeeting} day={day} />
            </section>
          )}
          {page && page.meetings.length > 0 && (
            <section aria-labelledby={`${ids}-meetings`}>
              <Head id={`${ids}-meetings`}>{strings.meetings}</Head>
              <ul>
                {page.meetings.map((meeting) => (
                  <li key={meeting.id}>
                    <button
                      type="button"
                      onClick={() => onOpenMeeting(meeting.id)}
                      className="sheet-row point-row w-full text-left"
                    >
                      <span className="sheet-point font-semibold [overflow-wrap:anywhere]">{meeting.title}</span>
                      <span className="sheet-mid on-rule" />
                      <span className="sheet-quotes text-[13px] leading-5 text-muted tabular-nums">
                        {meetingLine(meeting)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
        <Forget name={name} onForget={props.onForget} />
      </div>
    </div>
  );
}

/** A group of rows within a section, under its small muted head. */
function Group({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id}>
      <GroupHead id={id}>{title}</GroupHead>
      <ul>{children}</ul>
    </section>
  );
}

function Muted({ children }: { children: ReactNode }) {
  return (
    <div className="sheet-row">
      <p className="sheet-point text-muted">{children}</p>
      <span className="sheet-mid on-rule" />
    </div>
  );
}

/** A point from the last 1:1 | the time tabs of the lines it came from | its meeting. */
function LastRow({ block, where, onOpen }: { block: NoteBlock; where: string; onOpen: (utteranceId?: string) => void }) {
  const lines = block.citations.filter((c, i) => block.citations.findIndex((d) => d.utterance_id === c.utterance_id) === i);
  return (
    <li className="group/row sheet-row point-row">
      <p className="sheet-point">{block.text}</p>
      <span className="sheet-mid on-rule">
        {lines.map((line) => (
          <button
            key={line.utterance_id}
            type="button"
            onClick={() => onOpen(line.utterance_id)}
            aria-label={strings.jumpTo(formatClock(line.start_ms))}
            className="time-tab"
          >
            {formatClock(line.start_ms)}
          </button>
        ))}
      </span>
      <div className="sheet-quotes">
        <MeetingLink label={where} onOpen={() => onOpen()} />
      </div>
    </li>
  );
}

interface CatchMeUpProps {
  page: PersonPage;
  status: BriefStatus | undefined;
  onWrite: () => void;
  onOpen: (meetingId: string) => void;
  day: (epochMs: number) => string;
}

// The brief: while it is written only its band row shows (it appears once, complete); a failure
// or a brief none of whose points could be checked says so above the last brief; each point
// links the meetings it cites. Write a brief, or Write again, under it, once a 1:1 has a note.
function CatchMeUp({ page, status, onWrite, onOpen, day }: CatchMeUpProps) {
  const button = useRef<HTMLButtonElement>(null);
  const refocus = useRef(false);
  const writing = status?.state === "writing";
  // Pressing the button disables it, which drops its focus: give it back once the brief is in,
  // unless the owner has moved on.
  useEffect(() => {
    if (writing || !refocus.current) return;
    refocus.current = false;
    const active = document.activeElement;
    if (!active || active === document.body) button.current?.focus();
  }, [writing]);
  const tried = status?.state === "failed" || status?.state === "unchecked";
  const points = page.brief?.points ?? [];
  return (
    <>
      {writing ? (
        <div role="status" className="sheet-row bg-band">
          <p className="sheet-point caps py-3.5 text-[15px] leading-[18px] text-rule-ink">{strings.writingBrief}</p>
          <span aria-hidden="true" className="sheet-mid progress-mid">
            <span />
          </span>
        </div>
      ) : (
        <>
          {status?.state === "failed" && (
            <div role="alert" className="sheet-row bg-band-deep">
              <p className="sheet-point py-3.5">{briefFailureText(status.reason)}</p>
              <span className="sheet-mid on-rule" />
            </div>
          )}
          {status?.state === "unchecked" && (
            <div className="sheet-row bg-band">
              <p className="sheet-point py-3.5">{strings.briefUnchecked}</p>
              <span className="sheet-mid on-rule" />
            </div>
          )}
          {points.length > 0 && (
            <ul>
              {points.map((point, index) => (
                <li key={index} className="group/row sheet-row point-row">
                  <p className="sheet-point">{point.text}</p>
                  <span className="sheet-mid on-rule" />
                  <div className="sheet-quotes flex flex-col items-start gap-1">
                    {point.meetings.map((meeting) => (
                      <MeetingLink
                        key={meeting.id}
                        label={`${meeting.title} · ${day(meeting.started_at)}`}
                        onOpen={() => onOpen(meeting.id)}
                      />
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      <div className="sheet-row">
        <div className="sheet-point pt-3 pb-2">
          {page.meetings.some((meeting) => meeting.has_note) ? (
            <>
              <button
                ref={button}
                type="button"
                disabled={writing}
                onClick={() => {
                  refocus.current = true;
                  onWrite();
                }}
                className="rounded-lg bg-ink px-4 py-2 font-semibold text-pad transition-colors enabled:hover:bg-ink/88 disabled:cursor-not-allowed disabled:bg-ink/40"
              >
                {points.length > 0 || tried ? strings.writeAgain : strings.writeBrief}
              </button>
              <div aria-live="polite">
                {status?.state === "refused" && (
                  <p className="mt-2 text-[13px] leading-5 text-muted">
                    {status.reason === "busy"
                      ? strings.briefBusy
                      : status.reason === "no_notes"
                        ? strings.briefNeedsNotes
                        : briefFailureText(undefined)}
                  </p>
                )}
              </div>
            </>
          ) : (
            <p className="text-muted">{strings.briefNeedsNotes}</p>
          )}
        </div>
        <span className="sheet-mid on-rule" />
      </div>
    </>
  );
}

interface NameTitleProps {
  ref: Ref<HTMLHeadingElement>;
  name: string;
  onRename: (name: string) => Promise<RenameRefusal | null>;
}

// The name as the page's title, renamed in place as a meeting's title is: the pencil opens an
// input in the same display type on the band. Enter saves; a name someone else has, or "You", is
// refused under it with the input kept open; Escape cancels. Either puts the focus on the pencil.
function NameTitle({ ref, name, onRename }: NameTitleProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name);
  const [refusal, setRefusal] = useState("");
  const button = useRef<HTMLButtonElement>(null);
  const open = useRef(false); // the input, for a reply that lands after it closed
  const saving = useRef(false);
  const refocus = useRef(false);
  const refusalId = useId();

  useEffect(() => {
    if (editing || !refocus.current) return;
    refocus.current = false;
    button.current?.focus();
  }, [editing]);

  function begin() {
    open.current = true;
    setDraft(name);
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
    const refused = await onRename(draft).finally(() => {
      saving.current = false;
    });
    if (!open.current) return;
    if (refused === null) end(true);
    else if (refused === "taken") setRefusal(strings.nameTaken);
    else if (refused === "reserved") setRefusal(strings.nameReserved);
  }

  if (!editing) {
    return (
      <div className="flex items-start gap-2">
        <h1
          ref={ref}
          tabIndex={-1}
          className="line-clamp-2 min-w-0 font-display text-[clamp(2.25rem,4.6vw,3.75rem)] leading-[0.95] font-extrabold text-balance [overflow-wrap:anywhere] outline-none"
        >
          {name}
        </h1>
        <button
          ref={button}
          type="button"
          aria-label={strings.renamePerson}
          onClick={begin}
          className="mt-[0.15em] inline-flex size-8 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-band hover:text-ink"
        >
          <PencilIcon />
        </button>
      </div>
    );
  }
  return (
    <>
      <input
        aria-label={strings.personName}
        aria-describedby={refusal ? refusalId : undefined}
        aria-invalid={refusal ? true : undefined}
        autoFocus
        autoComplete="off"
        spellCheck={false}
        value={draft}
        maxLength={MAX_NAME}
        onChange={(event) => {
          setDraft(event.target.value);
          setRefusal("");
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault(); // no keypress: it would press the pencil the focus returns to
            void save();
          }
          if (event.key === "Escape") end(true);
        }}
        onBlur={() => {
          if (open.current) end(false);
        }}
        className="w-full rounded-lg bg-band px-2 font-display text-[clamp(2.25rem,4.6vw,3.75rem)] leading-[1.1] font-extrabold"
      />
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

// Forget this person (D14), quiet at the foot of the page. It asks first, in place, because it
// deletes their brief: Forget, or Keep (which has the focus); Keep and Escape put the focus back.
function Forget({ name, onForget }: { name: string; onForget: () => Promise<boolean> }) {
  const [asking, setAsking] = useState(false);
  const [failed, setFailed] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const keep = useRef<HTMLButtonElement>(null);
  const group = useRef<HTMLDivElement>(null);
  const back = useRef(false);
  const sentence = useId();

  useEffect(() => {
    if (asking) {
      keep.current?.focus();
      group.current?.scrollIntoView({ block: "nearest" }); // the whole question, not just Keep
    } else if (back.current) {
      back.current = false;
      button.current?.focus();
    }
  }, [asking]);

  function cancel() {
    back.current = true;
    setAsking(false);
  }

  if (!asking) {
    return (
      <div className="mt-8">
        <button
          ref={button}
          type="button"
          onClick={() => {
            setFailed(false);
            setAsking(true);
          }}
          className="rounded-sm text-[13px] leading-5 text-muted underline decoration-transparent underline-offset-[3px] hover:text-ink hover:decoration-rule"
        >
          {strings.forgetPerson}
        </button>
      </div>
    );
  }
  return (
    <div
      ref={group}
      role="group"
      aria-labelledby={sentence}
      onKeyDown={(event) => {
        if (event.key === "Escape") cancel();
      }}
      className="mt-8 max-w-[40rem] rounded-[10px] bg-band-deep px-4 py-3"
    >
      <p id={sentence} className="font-semibold">
        {strings.forgetConfirm(name)}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={async () => setFailed(!(await onForget()))}
          className="rounded-lg bg-ink px-4 py-2 font-semibold text-pad transition-colors hover:bg-ink/88"
        >
          {strings.forgetYes}
        </button>
        <button
          ref={keep}
          type="button"
          onClick={cancel}
          className="rounded-lg bg-pad px-4 py-2 font-semibold transition-colors hover:bg-band"
        >
          {strings.forgetNo}
        </button>
      </div>
      {failed && (
        <p role="alert" className="mt-2 text-[13px] leading-5">
          {strings.forgetFailed}
        </p>
      )}
    </div>
  );
}
