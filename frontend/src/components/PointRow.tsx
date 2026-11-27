import type { ItemStatus, NoteBlock, Utterance } from "@/bridge";
import { CheckIcon } from "@/components/icons";
import { formatClock } from "@/format";
import { cn } from "@/lib/utils";
import { strings } from "@/strings";

interface PointRowProps {
  block: NoteBlock;
  quotes: Utterance[];
  onCite: (id: string) => void;
  /** Given, an action item gets a Done box in its point cell. */
  onItemStatus?: (id: string, status: ItemStatus) => void;
}

/** An action item names its owner first ("You: send …"), as its record says (RB41). */
function ownerOf(block: NoteBlock): { owner: string | null; rest: string } {
  const owner = block.item?.kind === "action_item" ? block.item.owner : null;
  if (owner && block.text.startsWith(`${owner}: `)) return { owner, rest: block.text.slice(owner.length + 2) };
  return { owner: null, rest: block.text };
}

// One point on the sheet: the point | its time tabs on the rule | the lines it came from, and
// the owner's own line when it came from their notes. Note points and answers share it.
export function PointRow({ block, quotes, onCite, onItemStatus }: PointRowProps) {
  const { owner, rest } = ownerOf(block);
  const item = block.item?.kind === "action_item" ? block.item : undefined;
  const tick = item && onItemStatus ? (done: boolean) => onItemStatus(item.id, done ? "done" : "open") : undefined;
  const done = item?.status === "done";
  const seen = new Set<string>();
  const times = block.citations.filter((c) => {
    if (seen.has(c.utterance_id)) return false;
    seen.add(c.utterance_id);
    return true;
  });
  const point = owner ? (
    <>
      <b className="font-bold">{owner}:</b> {rest}
    </>
  ) : (
    rest
  );
  return (
    <li className="sheet-row point-row">
      {tick ? (
        <div className="sheet-point flex items-start gap-2.5">
          {/* The Done box, drawn like a time tab on the point's first line: ticked, it fills rule green.
              The label is positioned so the sr-only input stays in the row: a tick or Tab then
              scrolls the note to the row, never the whole window. */}
          <label className="group relative flex h-[23px] flex-none cursor-pointer items-center">
            <input
              type="checkbox"
              className="peer sr-only"
              checked={done}
              aria-label={strings.markDone(block.text)}
              onChange={(event) => tick(event.target.checked)}
            />
            <span
              aria-hidden="true"
              className="inline-flex size-4 items-center justify-center rounded-sm border-[1.5px] border-rule/60 text-pad transition-colors group-hover:border-rule peer-checked:border-rule peer-checked:bg-rule peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-rule"
            >
              {done && <CheckIcon width={12} height={12} strokeWidth={2} />}
            </span>
          </label>
          <p className={cn("min-w-0", done && "text-muted line-through")}>{point}</p>
        </div>
      ) : (
        <p className="sheet-point">{point}</p>
      )}
      <span className="sheet-mid on-rule">
        {times.map((citation) => (
          <button
            key={citation.utterance_id}
            type="button"
            onClick={() => onCite(citation.utterance_id)}
            aria-label={strings.jumpTo(formatClock(citation.start_ms))}
            className="time-tab"
          >
            {formatClock(citation.start_ms)}
          </button>
        ))}
      </span>
      <div className="sheet-quotes">
        {quotes.map((line) => (
          <Quote key={line.id} line={line} />
        ))}
        {block.user_quote && (
          <p className="quote">
            <span className="caps mr-1.5 text-[14px] text-you">{strings.fromYourNotes}</span>
            <q>{block.user_quote.text}</q>
          </p>
        )}
      </div>
    </li>
  );
}

/** A transcript line on the sheet's far side: who said it, in their ink, then the words. */
export function Quote({ line }: { line: Utterance }) {
  return (
    <p className="quote">
      <span className={cn("caps mr-1.5 text-[14px]", line.channel === 0 ? "text-you" : "text-them")}>{line.speaker}</span>
      <q>{line.text}</q>
    </p>
  );
}
