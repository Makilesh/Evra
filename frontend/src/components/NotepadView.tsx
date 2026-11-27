import {
  type ClipboardEvent,
  type KeyboardEvent,
  type MouseEvent,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { MeetingSummary, NoteLine, Utterance } from "@/bridge";
import { Quote } from "@/components/PointRow";
import { formatClock } from "@/format";
import { cn } from "@/lib/utils";
import { CONTEXT_CHARS, MAX_LINE_CHARS, MAX_LINES, newLine, splitText, typedAt, typedNow } from "@/notepad";
import { strings } from "@/strings";

interface NotepadViewProps {
  lines: NoteLine[];
  meeting: MeetingSummary;
  utterances: Utterance[];
  isLive: boolean;
  /** The meeting has a note, so each line shows the transcript lines the note linked it to. */
  noted: boolean;
  onChange: (lines: NoteLine[]) => void;
  /** A typed time was pressed: open the transcript at that time (ms into the call). */
  onJump: (ms: number) => void;
  /** An empty pad opens with its line focused; not when the owner came along the tabs by keyboard. */
  focusOnOpen?: boolean;
}

/** Where the caret goes once the pad shows the change. */
interface Caret {
  id: string;
  at: number;
}

// My notes: the owner's lines on the note's sheet, one row each: the line | the time it was
// typed, on the rule | once the note is written, the transcript lines it was linked to. Enter
// starts the next line, Backspace in an empty one goes back to the end of the one before, and
// the arrow keys step between lines from a line's first or last row. While live, the last two
// transcript lines run under the pad.
export function NotepadView({
  lines,
  meeting,
  utterances,
  isLive,
  noted,
  onChange,
  onJump,
  focusOnOpen = true,
}: NotepadViewProps) {
  const [draft] = useState(newLine);
  const rows = lines.length > 0 ? lines : [draft];
  const byId = useMemo(() => new Map(utterances.map((u) => [u.id, u])), [utterances]);
  const fields = useRef(new Map<string, HTMLTextAreaElement>());
  const [caret, setCaret] = useState<Caret | null>(null);
  const opensFocused = useRef(lines.length === 0 && focusOnOpen);
  // The line a long paste is going into: the change the paste makes marks it.
  const pasting = useRef<string | null>(null);

  // An empty pad opens on its one line, ready to type.
  useEffect(() => {
    if (opensFocused.current) fields.current.get(draft.id)?.focus();
  }, [draft.id]);

  // A line just added, or the one before a line just removed, takes the caret once it is shown.
  useLayoutEffect(() => {
    const field = caret ? fields.current.get(caret.id) : undefined;
    if (!caret || !field) return;
    field.focus();
    field.setSelectionRange(caret.at, caret.at);
    setCaret(null);
  }, [caret, lines]);

  function change(next: NoteLine[], moveTo?: Caret) {
    onChange(next);
    if (moveTo) setCaret(moveTo);
  }

  function type(index: number, text: string) {
    const line = rows[index];
    const pasted = line.pasted || pasting.current === line.id;
    pasting.current = null;
    change(rows.toSpliced(index, 1, { ...typedNow(line, text), pasted }));
  }

  // Up from a line's first row and down from its last go to the line before or after, at the
  // same place along it as far as that line goes.
  function step(field: HTMLTextAreaElement, to: number) {
    const target = rows[to];
    const next = fields.current.get(target.id);
    if (!next) return;
    const at = Math.min(field.selectionStart, target.text.length);
    next.focus();
    next.setSelectionRange(at, at);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>, index: number) {
    if (event.nativeEvent.isComposing || event.altKey || event.ctrlKey || event.metaKey) return;
    const field = event.currentTarget;
    const plain = !event.shiftKey && field.selectionStart === field.selectionEnd;
    if (event.key === "Enter") {
      event.preventDefault(); // one note a line: Enter starts the next one
      if (rows.length >= MAX_LINES) return;
      const added = newLine();
      change(rows.toSpliced(index + 1, 0, added), { id: added.id, at: 0 });
    } else if (event.key === "Backspace" && field.value === "" && index > 0) {
      event.preventDefault();
      const before = rows[index - 1];
      change(rows.toSpliced(index, 1), { id: before.id, at: before.text.length });
    } else if (event.key === "ArrowUp" && plain && index > 0 && caretRows(field).first) {
      event.preventDefault();
      step(field, index - 1);
    } else if (event.key === "ArrowDown" && plain && index < rows.length - 1 && caretRows(field).last) {
      event.preventDefault();
      step(field, index + 1);
    }
  }

  function onPaste(event: ClipboardEvent<HTMLTextAreaElement>, index: number) {
    const pasted = event.clipboardData.getData("text/plain").replace(/\r\n?/g, "\n");
    const field = event.currentTarget;
    const line = rows[index];
    const long = pasted.length > CONTEXT_CHARS;
    const text = field.value.slice(0, field.selectionStart) + pasted + field.value.slice(field.selectionEnd);
    if (text.length <= MAX_LINE_CHARS) {
      pasting.current = long ? line.id : null; // the field takes it, and its change marks the line
      return;
    }
    // Too long for one line: it becomes as many lines as it needs, as many as the pad has room for.
    event.preventDefault();
    pasting.current = null;
    const [first, ...more] = splitText(text).slice(0, MAX_LINES - rows.length + 1);
    const added = more.map((piece) => ({ ...typedNow(newLine(), piece), pasted: long }));
    const kept = { ...typedNow(line, first), pasted: line.pasted || long };
    const end = added.at(-1) ?? kept;
    change(rows.toSpliced(index, 1, kept, ...added), { id: end.id, at: end.text.length });
  }

  // A click on the pad below the lines carries on from the last one.
  function onPadClick(event: MouseEvent<HTMLDivElement>) {
    if (event.target !== event.currentTarget) return;
    const last = rows[rows.length - 1];
    setCaret({ id: last.id, at: last.text.length });
  }

  return (
    <div className="flex h-full flex-col">
      {/* While live, the pad fades out over its last 28px above the transcript lines; its
          scroll padding stops scrolling to a line, or to the caret, clear of the fade. */}
      <div
        onClick={onPadClick}
        className={cn(
          "min-h-0 flex-1 overflow-y-auto px-[var(--gutter)]",
          isLive
            ? "scroll-pb-8 pb-8 [mask-image:linear-gradient(to_bottom,black_calc(100%-28px),transparent)]"
            : "pb-12",
        )}
      >
        <ol aria-label={strings.notesTab} className="sheet measure -mx-2.5 pt-3">
          {rows.map((line, index) => {
            const at = typedAt(line, meeting);
            const linked = noted ? (line.aligned ?? []).flatMap((a) => byId.get(a.utterance_id) ?? []) : [];
            return (
              <li key={line.id} className="sheet-row pad-row">
                {/* The whole cell takes a click for its line. */}
                <label className="sheet-point">
                  <textarea
                    ref={(field) => {
                      if (field) fields.current.set(line.id, field);
                      return () => {
                        fields.current.delete(line.id);
                      };
                    }}
                    value={line.text}
                    rows={1}
                    maxLength={MAX_LINE_CHARS}
                    aria-label={strings.noteLine(index + 1)}
                    placeholder={rows.length === 1 ? strings.notesPlaceholder : undefined}
                    onChange={(event) => type(index, event.target.value)}
                    // the whole field and its focus ring in view, also at the pad's edge
                    onFocus={(event) => event.currentTarget.scrollIntoView({ block: "nearest" })}
                    onKeyDown={(event) => onKeyDown(event, index)}
                    onPaste={(event) => onPaste(event, index)}
                    className="block w-full scroll-my-1.5 resize-none rounded-sm bg-transparent p-0 field-sizing-content placeholder:text-muted"
                  />
                </label>
                <span className="sheet-mid on-rule">
                  {at !== null && (
                    <button
                      type="button"
                      onClick={() => onJump(at)}
                      aria-label={strings.jumpTo(formatClock(at))}
                      className="time-tab"
                    >
                      {formatClock(at)}
                    </button>
                  )}
                </span>
                {linked.length > 0 && (
                  <div className="sheet-quotes">
                    {linked.map((u) => (
                      <Quote key={u.id} line={u} />
                    ))}
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      </div>
      {isLive && <LiveStrip utterances={utterances} />}
    </div>
  );
}

// While live, under the pad and on the same rule: the last two transcript lines on the far side,
// where a line's links show once the note is written, then where the next one will land.
function LiveStrip({ utterances }: { utterances: Utterance[] }) {
  const last = utterances.slice(-2);
  return (
    <div className="measure-pad shrink-0 px-[var(--gutter)] pb-3">
      <div className="sheet measure -mx-2.5">
        {last.length > 0 && (
          <ol aria-label={strings.transcriptTab}>
            {last.map((u) => (
              <li key={u.id} className="sheet-row">
                <span className="sheet-mid on-rule">
                  <span className="line-time">{formatClock(u.start_ms)}</span>
                </span>
                {/* Clamped inside the cell, so a cut line never shows in the cell's padding. */}
                <div className="sheet-quotes">
                  <p className="quote line-clamp-2 short:line-clamp-1">
                    <span className={cn("caps mr-1.5 text-[14px]", u.channel === 0 ? "text-you" : "text-them")}>
                      {u.speaker}
                    </span>
                    {u.text}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        )}
        <div role="status" className="sheet-row">
          <span className="sheet-mid on-rule-fade min-h-9">
            <span aria-hidden="true" className="listening-dot" />
          </span>
          <span className="sheet-quotes caps text-[14px] text-muted">{strings.listening}</span>
        </div>
      </div>
    </div>
  );
}

/** Whether the caret is on the field's first and its last visual row. A field without layout
 *  (as in tests) counts as one row. */
function caretRows(field: HTMLTextAreaElement): { first: boolean; last: boolean } {
  const style = getComputedStyle(field);
  const row = parseFloat(style.lineHeight);
  const count = Math.round(field.scrollHeight / row);
  if (!(row > 0) || !(count > 1)) return { first: true, last: true };
  // A hidden copy of the text up to the caret, wrapped as the field wraps it, shows its row.
  const copy = document.createElement("div");
  copy.style.cssText = `position:absolute;visibility:hidden;top:0;left:0;white-space:pre-wrap;overflow-wrap:break-word;width:${field.clientWidth}px;font:${style.font};letter-spacing:${style.letterSpacing}`;
  copy.textContent = field.value.slice(0, field.selectionStart);
  const mark = copy.appendChild(document.createElement("span"));
  mark.textContent = "\u200b"; // zero-width: where the caret is
  document.body.append(copy);
  const at = Math.round(mark.offsetTop / row);
  copy.remove();
  return { first: at <= 0, last: at >= count - 1 };
}
