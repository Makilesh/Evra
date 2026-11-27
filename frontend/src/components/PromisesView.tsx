import { useId, useLayoutEffect, useRef, type FocusEvent } from "react";
import type { ItemStatus, OpenPromise } from "@/bridge";
import { DoneBox } from "@/components/PointRow";
import { dayLabel, formatClock } from "@/format";
import { cn } from "@/lib/utils";
import { strings } from "@/strings";
import type { Direction, ShownPromises } from "@/usePeople";

interface PromisesViewProps {
  /** Null until Python has listed them. */
  promises: ShownPromises | null;
  onStatus: (id: string, status: ItemStatus) => void;
  /** Open a promise's meeting; at the transcript line it cites, when given. */
  onOpenMeeting: (meetingId: string, utteranceId?: string) => void;
  now?: () => number;
}

const SECTIONS: { direction: Direction; title: string }[] = [
  { direction: "you", title: strings.youPromised },
  { direction: "them", title: strings.theyPromised },
];

/** Where the focus is among the rows: the control, and its row. */
interface Focused {
  control: Element;
  id: string;
  direction: Direction;
}

// Every open promise across the 1:1s on the note's sheet, what you promised, then what they did.
// It scrolls in its own scroller, as every page does (#root clips, RB65).
export function PromisesView({ promises, onStatus, onOpenMeeting, now = Date.now }: PromisesViewProps) {
  const ids = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const sheet = useRef<HTMLDivElement>(null);
  const focused = useRef<Focused | null>(null);
  const before = useRef<ShownPromises | null>(null); // the rows as the last render showed them

  /** The control and its row; null outside the rows. */
  function locate(control: Element): Focused | null {
    const row = control.closest<HTMLElement>("[data-promise-id]");
    const id = row?.dataset.promiseId;
    const direction = row?.closest<HTMLElement>("[data-direction]")?.dataset.direction as Direction | undefined;
    return id && direction ? { control, id, direction } : null;
  }

  // A control that goes with the focus in it hands the focus to the Done box now in its row's
  // place: its own row's when the row stays (a refused set-aside's Undo goes), else the row that
  // came after it, else the one before, else the title. The neighbours are the rows as last shown,
  // so rows that left above it meanwhile don't move the target. The keyboard keeps its place.
  useLayoutEffect(() => {
    const shown = before.current;
    before.current = promises;
    const last = focused.current;
    if (!last || last.control.isConnected) return;
    const active = document.activeElement;
    if (active && active !== document.body) {
      focused.current = sheet.current?.contains(active) ? locate(active) : null; // it went elsewhere
      return;
    }
    focused.current = null;
    const present = new Set(promises?.[last.direction].map((r) => r.promise.id));
    const then = shown?.[last.direction].map((r) => r.promise.id) ?? [];
    const at = Math.max(0, then.indexOf(last.id));
    const next = [...then.slice(at), ...then.slice(0, at).reverse()].find((id) => present.has(id));
    const rows = Array.from(sheet.current?.querySelectorAll<HTMLElement>("[data-promise-id]") ?? []);
    const box = rows.find((row) => row.dataset.promiseId === next)?.querySelector<HTMLElement>('input[type="checkbox"]');
    (box ?? heading.current)?.focus();
  });

  function track(event: FocusEvent<HTMLDivElement>) {
    focused.current = locate(event.target);
  }

  // The focus left the rows (Tab, a click elsewhere): forget it. A control that leaves with its
  // row is gone from the page by then, and the effect above has moved the focus already.
  function untrack(event: FocusEvent<HTMLDivElement>) {
    const control = event.target;
    queueMicrotask(() => {
      const away = !sheet.current?.contains(document.activeElement);
      if (focused.current?.control === control && control.isConnected && away) focused.current = null;
    });
  }

  const empty = promises !== null && promises.you.length === 0 && promises.them.length === 0;
  return (
    <div className="enter h-full overflow-y-auto">
      <div className="measure-pad px-[var(--gutter)] pt-[30px] pb-12">
        <h1
          ref={heading}
          tabIndex={-1}
          className="font-display text-[clamp(2.25rem,4.6vw,3.75rem)] leading-[0.95] font-extrabold outline-none"
        >
          {strings.openPromises}
        </h1>
        {empty ? (
          <p className="mt-6 max-w-[40rem] text-muted">{strings.noPromises}</p>
        ) : (
          promises && (
            <div ref={sheet} onFocus={track} onBlur={untrack} className="sheet measure -mx-2.5 mt-4">
              {SECTIONS.filter(({ direction }) => promises[direction].length > 0).map(({ direction, title }) => (
                <section key={direction} aria-labelledby={`${ids}-${direction}`} data-direction={direction}>
                  <div className="sheet-row">
                    <h2
                      id={`${ids}-${direction}`}
                      className="sheet-point caps pt-[18px] pb-1 text-[15px] leading-[18px] text-rule"
                    >
                      {title}
                    </h2>
                    <span className="sheet-mid on-rule pt-[22px]">
                      <span className="detent" />
                    </span>
                  </div>
                  <ul>
                    {promises[direction].map((row) => (
                      <PromiseRow
                        key={row.promise.id}
                        promise={row.promise}
                        status={row.status}
                        onStatus={onStatus}
                        onOpenMeeting={onOpenMeeting}
                        now={now}
                      />
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )
        )}
      </div>
    </div>
  );
}

interface PromiseRowProps {
  promise: OpenPromise;
  /** As the window shows it: done or set aside, the row says so and offers Undo. */
  status: ItemStatus;
  onStatus: (id: string, status: ItemStatus) => void;
  onOpenMeeting: (meetingId: string, utteranceId?: string) => void;
  now?: () => number;
}

/** One promise on the sheet: its Done box, the task and when it is due | the time tab of the line
 *  it came from, on the rule | who, which meeting and when, opening that meeting. Ticked, it says
 *  Done with Undo; "Not a promise" sets it aside, with Undo too. A person's page shows the same
 *  rows. */
export function PromiseRow({ promise, status, onStatus, onOpenMeeting, now = Date.now }: PromiseRowProps) {
  const box = useRef<HTMLInputElement>(null);
  const undo = useRef<HTMLButtonElement>(null);
  const toUndo = useRef(false); // "Not a promise" was pressed: its Undo takes the focus
  useLayoutEffect(() => {
    if (toUndo.current && status === "dismissed") undo.current?.focus();
    toUndo.current = false;
  }, [status]);
  const done = status === "done";
  const aside = status === "dismissed";
  // its due date once: a task that says it already needs no second (as the note shows it)
  const due = promise.due && !promise.text.toLowerCase().includes(promise.due.toLowerCase()) ? promise.due : null;
  const who = promise.person?.name ?? strings.them;
  const where = [who, promise.meeting_title, dayLabel(promise.started_at, now())].join(" · ");
  const line = promise.utterance_id;
  return (
    <li data-promise-id={promise.id} className="group/row sheet-row point-row">
      <div className="sheet-point flex items-start gap-2.5">
        <DoneBox
          ref={box}
          checked={done}
          label={strings.markDone(promise.text)}
          onChange={(checked) => onStatus(promise.id, checked ? "done" : "open")}
        />
        <div className="min-w-0">
          {/* set aside, it goes muted, but is not struck through: it wasn't done */}
          <p className={cn((done || aside) && "text-muted", done && "line-through")}>{promise.text}</p>
          <p className="text-[13px] leading-5 text-muted tabular-nums">
            {done || aside ? (
              <>
                <span className={cn("font-semibold", done && "text-rule-ink")}>
                  {done ? strings.done : strings.setAside}
                </span>
                {" · "}
                <button
                  ref={undo}
                  type="button"
                  onClick={() => {
                    box.current?.focus(); // the keyboard stays on the row, whose Undo goes
                    onStatus(promise.id, "open");
                  }}
                  className="ml-0.5 rounded-sm font-semibold text-ink underline decoration-rule underline-offset-[3px] hover:decoration-2"
                >
                  {strings.undo}
                </button>
              </>
            ) : (
              <>
                {due && `${due} · `}
                <button
                  type="button"
                  onClick={() => {
                    toUndo.current = true;
                    onStatus(promise.id, "dismissed");
                  }}
                  className={cn(
                    "rounded-sm underline decoration-transparent underline-offset-[3px] hover:text-ink hover:decoration-rule",
                    due && "ml-0.5", // after "due · ", the focus ring clears the dot
                  )}
                >
                  {strings.notAPromise}
                </button>
              </>
            )}
          </p>
        </div>
      </div>
      <span className="sheet-mid on-rule">
        {line !== null && promise.start_ms !== null && (
          <button
            type="button"
            onClick={() => onOpenMeeting(promise.meeting_id, line)}
            aria-label={strings.jumpTo(formatClock(promise.start_ms))}
            className="time-tab"
          >
            {formatClock(promise.start_ms)}
          </button>
        )}
      </span>
      <div className="sheet-quotes">
        <button
          type="button"
          onClick={() => onOpenMeeting(promise.meeting_id)}
          className="rounded-sm text-left text-[13px] leading-5 text-muted underline decoration-rule/50 underline-offset-[3px] group-focus-within/row:text-ink group-hover/row:text-ink hover:decoration-rule hover:decoration-2"
        >
          {where}
        </button>
      </div>
    </li>
  );
}
