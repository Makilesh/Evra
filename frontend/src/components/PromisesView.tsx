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

/** Where the focus was among the rows: the control, and its row's place. */
interface Focused {
  control: Element;
  direction: Direction;
  index: number;
}

// Every open promise across the 1:1s on the note's sheet, what you promised, then what they did.
// It scrolls in its own scroller, as every page does (#root clips, RB65).
export function PromisesView({ promises, onStatus, onOpenMeeting, now = Date.now }: PromisesViewProps) {
  const ids = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const sheet = useRef<HTMLDivElement>(null);
  const focused = useRef<Focused | null>(null);

  // A row that leaves with the focus in it (its 5 seconds of Undo are up, or it was not a promise)
  // hands the focus to the Done box of the row now in its place, else to the title, so the
  // keyboard keeps its place on the page.
  useLayoutEffect(() => {
    const last = focused.current;
    if (!last || last.control.isConnected) return;
    focused.current = null;
    if (document.activeElement && document.activeElement !== document.body) return; // it went elsewhere
    const section = sheet.current?.querySelector(`[data-direction="${last.direction}"]`);
    const boxes = Array.from(section?.querySelectorAll<HTMLElement>('input[type="checkbox"]') ?? []);
    (boxes[Math.min(last.index, boxes.length - 1)] ?? heading.current)?.focus();
  });

  function track(event: FocusEvent<HTMLDivElement>) {
    const row = event.target.closest<HTMLElement>("[data-promise-id]");
    const direction = row?.closest<HTMLElement>("[data-direction]")?.dataset.direction as Direction | undefined;
    const index = direction ? (promises?.[direction].findIndex((r) => r.promise.id === row?.dataset.promiseId) ?? -1) : -1;
    focused.current = direction && index >= 0 ? { control: event.target, direction, index } : null;
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
  /** As the window shows it: ticked done, the row says so and offers Undo. */
  status: ItemStatus;
  onStatus: (id: string, status: ItemStatus) => void;
  onOpenMeeting: (meetingId: string, utteranceId?: string) => void;
  now?: () => number;
}

/** One promise on the sheet: its Done box, the task and when it is due | the time tab of the line
 *  it came from, on the rule | who, which meeting and when, opening that meeting. Ticked, it says
 *  Done with Undo; "Not a promise" sets it aside. A person's page shows the same rows. */
export function PromiseRow({ promise, status, onStatus, onOpenMeeting, now = Date.now }: PromiseRowProps) {
  const box = useRef<HTMLInputElement>(null);
  const done = status === "done";
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
          <p className={cn(done && "text-muted line-through")}>{promise.text}</p>
          <p className="text-[13px] leading-5 text-muted tabular-nums">
            {done ? (
              <>
                <span className="font-semibold text-rule-ink">{strings.done}</span>
                {" · "}
                <button
                  type="button"
                  onClick={() => {
                    box.current?.focus(); // the keyboard stays on the row, whose Undo goes
                    onStatus(promise.id, "open");
                  }}
                  className="rounded-sm font-semibold text-ink underline decoration-rule underline-offset-[3px] hover:decoration-2"
                >
                  {strings.undo}
                </button>
              </>
            ) : (
              <>
                {due && `${due} · `}
                <button
                  type="button"
                  onClick={() => onStatus(promise.id, "dismissed")}
                  className="rounded-sm underline decoration-transparent underline-offset-[3px] hover:text-ink hover:decoration-rule"
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
