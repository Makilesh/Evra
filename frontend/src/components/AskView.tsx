import { type FormEvent, type Ref, useEffect, useMemo, useRef, useState } from "react";
import type { AskRefusal, Question, Utterance } from "@/bridge";
import { PointRow } from "@/components/PointRow";
import { cn } from "@/lib/utils";
import { noteQuotes } from "@/note";
import { askFailureText, askRefusalText, strings } from "@/strings";

interface AskViewProps {
  questions: Question[];
  utterances: Utterance[];
  isLive: boolean;
  onAsk: (text: string) => Promise<AskRefusal | null>;
  onPrepare: () => void;
  onCite: (utteranceId: string) => void;
}

const MAX_QUESTION = 500;

// Ask: the meeting's questions as a thread on the note sheet, each answer a cited point beside
// the lines it came from, and the form fixed under the thread. One question at a time, and
// none while the meeting is being recorded.
export function AskView({ questions, utterances, isLive, onAsk, onPrepare, onCite }: AskViewProps) {
  const byId = useMemo(() => new Map(utterances.map((u) => [u.id, u])), [utterances]);
  const [draft, setDraft] = useState("");
  const [refusal, setRefusal] = useState<AskRefusal | null>(null);
  const [announced, setAnnounced] = useState("");
  const busy = isLive || questions.some((q) => q.state === "asking");
  const newestAsking = questions.at(-1)?.state === "asking";
  const box = useRef<HTMLInputElement>(null);
  const newest = useRef<HTMLElement>(null);
  const shown = useRef({ count: questions.length, asking: newestAsking });
  const prepared = useRef(false);
  const sending = useRef(false);
  const refocus = useRef(false);

  // An answer landing is announced once: a question left "asking" (or arrived settled).
  const settled = questions.filter((q) => q.state !== "asking").length;
  const [seenSettled, setSeenSettled] = useState(settled);
  if (settled !== seenSettled) {
    setSeenSettled(settled);
    if (settled > seenSettled) setAnnounced(strings.askAnswered);
  }

  // Python reads the meeting ahead while the owner types: once, when the tab opens.
  useEffect(() => {
    if (prepared.current) return;
    prepared.current = true;
    if (!isLive && utterances.length > 0) onPrepare();
  }, [isLive, utterances.length, onPrepare]);

  // The newest question comes into view when it is asked, and again when its answer lands below
  // it; "nearest" moves the thread only as far as that takes.
  useEffect(() => {
    const was = shown.current;
    shown.current = { count: questions.length, asking: newestAsking };
    const answered = questions.length === was.count && was.asking && !newestAsking;
    if (questions.length > was.count || answered) newest.current?.scrollIntoView({ block: "nearest" });
  }, [questions.length, newestAsking]);

  // Disabling the box while an answer is pending drops its focus: give it back once the answer
  // is in, unless the owner has moved on to something else.
  useEffect(() => {
    if (busy || !refocus.current) return;
    refocus.current = false;
    const active = document.activeElement;
    if (!active || active === document.body) box.current?.focus();
  }, [busy]);

  async function ask(text: string, typed = false) {
    if (sending.current) return;
    sending.current = true;
    refocus.current = true;
    setRefusal(null);
    setAnnounced("");
    const refused = await onAsk(text).catch(() => "busy" as const);
    sending.current = false;
    if (refused) {
      refocus.current = false;
      setRefusal(refused);
    } else if (typed) {
      setDraft("");
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if (text && !busy) void ask(text, true);
  }

  return (
    <div className="flex h-full flex-col">
      {/* The thread fades out over its last 28px above the form, as the rail's meetings do. */}
      <div className="min-h-0 flex-1 overflow-y-auto px-[var(--gutter)] pb-8 [mask-image:linear-gradient(to_bottom,black_calc(100%-28px),transparent)]">
        <div className="sheet measure -mx-2.5 pt-3">
          {questions.length === 0 ? (
            <p className="px-2.5 pt-5 text-muted">{isLive ? strings.askAfterRecording : strings.askIntro}</p>
          ) : (
            questions.map((question, index) => (
              <QuestionBlock
                key={question.id}
                ref={index === questions.length - 1 ? newest : undefined}
                question={question}
                byId={byId}
                busy={busy}
                onAskAgain={() => void ask(question.text)}
                onCite={onCite}
              />
            ))
          )}
        </div>
      </div>
      {/* A short window keeps its room for the thread: the form tightens, and once there are
          questions the one-click ones step aside (typing still works). */}
      <form
        onSubmit={submit}
        className="measure-pad flex shrink-0 flex-col gap-3 px-[var(--gutter)] pt-3 pb-6 short:gap-2 short:pt-2 short:pb-3"
      >
        <div className={cn("flex flex-wrap gap-2", questions.length > 0 && "short:hidden")}>
          {strings.askSuggestions.map((text) => (
            <button
              key={text}
              type="button"
              disabled={busy}
              onClick={() => void ask(text)}
              className="rounded-lg bg-band px-3 py-1.5 text-[13px] leading-5 font-semibold transition-colors enabled:hover:bg-band-deep disabled:cursor-not-allowed disabled:bg-band/50 disabled:text-muted"
            >
              {text}
            </button>
          ))}
        </div>
        <div>
          <div className="flex gap-2">
            <input
              ref={box}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              aria-label={strings.askLabel}
              placeholder={strings.askPlaceholder}
              maxLength={MAX_QUESTION}
              autoComplete="off"
              disabled={busy}
              className="h-10 min-w-0 flex-1 rounded-[10px] bg-band px-3 text-ink placeholder:text-muted disabled:cursor-not-allowed disabled:bg-band/50 disabled:text-muted"
            />
            <button
              type="submit"
              disabled={busy}
              className="h-10 shrink-0 rounded-lg bg-ink px-4 font-semibold text-pad transition-colors enabled:hover:bg-ink/88 disabled:cursor-not-allowed disabled:bg-ink/40"
            >
              {strings.askButton}
            </button>
          </div>
          <div aria-live="polite">
            {refusal && <p className="mt-2 text-[13px] leading-5 text-muted">{askRefusalText(refusal)}</p>}
          </div>
        </div>
      </form>
      <p role="status" aria-live="polite" className="sr-only">
        {announced}
      </p>
    </div>
  );
}

interface QuestionBlockProps {
  ref?: Ref<HTMLElement>;
  question: Question;
  byId: Map<string, Utterance>;
  busy: boolean;
  onAskAgain: () => void;
  onCite: (utteranceId: string) => void;
}

// A question heads its rows, with a detent on the rule; its answer follows on the sheet.
// Scrolled into view, it stops clear of the thread's 28px fade.
function QuestionBlock({ ref, question, ...answer }: QuestionBlockProps) {
  const heading = `ask-${question.id}`;
  return (
    <section ref={ref} aria-labelledby={heading} className="scroll-mb-8">
      <div className="sheet-row">
        <h2 id={heading} className="sheet-point pt-[18px] pb-1 font-semibold [overflow-wrap:anywhere]">
          {question.text}
        </h2>
        <span className="sheet-mid on-rule pt-[24px]">
          <span className="detent" />
        </span>
      </div>
      <Answer question={question} {...answer} />
    </section>
  );
}

function Answer({ question, byId, busy, onAskAgain, onCite }: Omit<QuestionBlockProps, "ref">) {
  switch (question.state) {
    case "asking":
      return (
        <div className="sheet-row bg-band">
          <p className="sheet-point caps py-3.5 text-[15px] leading-[18px] text-rule-ink">{strings.askThinking}</p>
          <span aria-hidden="true" className="sheet-mid progress-mid">
            <span />
          </span>
        </div>
      );
    case "answered":
      return (
        <>
          <ul>
            {question.points.map((point, index) => (
              <PointRow key={index} block={point} quotes={noteQuotes(point, byId)} owners={false} onCite={onCite} />
            ))}
          </ul>
          {question.excerpt && (
            <div className="sheet-row">
              <p className="sheet-point text-[13px] leading-5 text-muted">{strings.askExcerpt}</p>
              <span className="sheet-mid on-rule" />
            </div>
          )}
        </>
      );
    case "not_found":
      return <BandRow text={strings.notDiscussed} />;
    case "unchecked":
      return <BandRow text={strings.askUnchecked} />;
    case "failed":
      return (
        <div className="sheet-row bg-band-deep">
          <p className="sheet-point py-3.5">{askFailureText(question.reason)}</p>
          <span className="sheet-mid on-rule" />
          <div className="sheet-quotes py-3.5">
            <button
              type="button"
              disabled={busy}
              onClick={onAskAgain}
              className="rounded-lg bg-ink px-3 py-1 font-semibold text-pad transition-colors enabled:hover:bg-ink/88 disabled:cursor-not-allowed disabled:bg-ink/40"
            >
              {strings.askAgain}
            </button>
          </div>
        </div>
      );
  }
}

function BandRow({ text }: { text: string }) {
  return (
    <div className="sheet-row bg-band">
      <p className="sheet-point py-3.5">{text}</p>
      <span className="sheet-mid on-rule" />
    </div>
  );
}
