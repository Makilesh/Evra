import { useRef } from "react";
import type { ItemStatus } from "@/bridge";
import { PromiseSections } from "@/components/PromiseSections";
import { strings } from "@/strings";
import type { ShownPromises } from "@/usePeople";

interface PromisesViewProps {
  /** Null until Python has listed them. */
  promises: ShownPromises | null;
  /** Nothing is shown yet and the last read of them failed. */
  unread: boolean;
  onStatus: (id: string, status: ItemStatus) => void;
  /** Open a promise's meeting; at the transcript line it cites, when given. */
  onOpenMeeting: (meetingId: string, utteranceId?: string) => void;
  now?: () => number;
}

// Every open promise across the 1:1s on the note's sheet, what you promised, then what they did.
// It scrolls in its own scroller, as every page does (#root clips, RB65).
export function PromisesView({ promises, unread, onStatus, onOpenMeeting, now = Date.now }: PromisesViewProps) {
  const heading = useRef<HTMLHeadingElement>(null);
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
        {promises === null && unread && <p className="mt-6 max-w-[40rem] text-muted">{strings.promisesUnread}</p>}
        {empty && <p className="mt-6 max-w-[40rem] text-muted">{strings.noPromises}</p>}
        {promises && (
          <PromiseSections
            promises={promises}
            onStatus={onStatus}
            onOpenMeeting={onOpenMeeting}
            fallback={heading}
            className={empty ? undefined : "sheet measure -mx-2.5 mt-4"}
            now={now}
          />
        )}
      </div>
    </div>
  );
}
