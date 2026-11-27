import { useRef } from "react";
import type { PersonSummary } from "@/bridge";
import { dayLabel } from "@/format";
import { useFocusOnLanding } from "@/landing";
import { strings } from "@/strings";
import { promisesOf, type ShownPromise, type ShownPromises } from "@/usePeople";

interface PeopleViewProps {
  people: PersonSummary[];
  /** Null until Python has listed them. */
  promises: ShownPromises | null;
  /** Nothing listed yet, and the last read failed. */
  promisesUnread: boolean;
  onOpenPerson: (personId: string) => void;
  now?: () => number;
}

const open = (rows: ShownPromise[]) => rows.filter((row) => row.status === "open").length;

// Everyone the owner has named, by name, on the note's sheet: when their last 1:1 was, and their
// open promises both ways, counted from the rows the window shows (the rail's count does the
// same). A row opens the person's page. The page scrolls in its own scroller (#root clips).
export function PeopleView({ people, promises, promisesUnread, onOpenPerson, now = Date.now }: PeopleViewProps) {
  const heading = useRef<HTMLHeadingElement>(null);
  useFocusOnLanding(heading);
  return (
    <div className="enter h-full overflow-y-auto">
      <div className="measure-pad px-[var(--gutter)] pt-[30px] pb-12">
        <h1
          ref={heading}
          tabIndex={-1}
          className="font-display text-[clamp(2.25rem,4.6vw,3.75rem)] leading-[0.95] font-extrabold outline-none"
        >
          {strings.people}
        </h1>
        {people.length === 0 ? (
          <p className="mt-6 max-w-[40rem] text-muted">{strings.noPeople}</p>
        ) : (
          <>
            {promises === null && promisesUnread && (
              <p className="mt-6 max-w-[40rem] text-muted">{strings.promisesUnread}</p>
            )}
            <ul className="sheet measure -mx-2.5 mt-4">
              {people.map((person) => {
                const theirs = promises && promisesOf(promises, person.id);
                return (
                  <li key={person.id}>
                    <button
                      type="button"
                      onClick={() => onOpenPerson(person.id)}
                      className="sheet-row point-row w-full text-left"
                    >
                      <span className="sheet-point">
                        <span className="block font-semibold [overflow-wrap:anywhere]">{person.name}</span>
                        {person.last_met !== null && (
                          <span className="block text-[13px] leading-5 text-muted tabular-nums">
                            {strings.lastMet(dayLabel(person.last_met, now()))}
                          </span>
                        )}
                      </span>
                      <span className="sheet-mid on-rule pt-[14px]">
                        <span className="detent" />
                      </span>
                      <span className="sheet-quotes text-[13px] leading-5 text-muted tabular-nums">
                        {theirs && strings.promisedCounts(open(theirs.you), open(theirs.them))}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
