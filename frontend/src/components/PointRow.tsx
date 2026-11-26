import type { NoteBlock, Utterance } from "@/bridge";
import { formatClock } from "@/format";
import { cn } from "@/lib/utils";
import { splitOwner } from "@/note";
import { strings } from "@/strings";

interface PointRowProps {
  block: NoteBlock;
  quotes: Utterance[];
  owners: boolean;
  onCite: (id: string) => void;
}

// One point on the sheet: the point | its time tabs on the rule | the lines it came from.
// Note points and answers to questions share it.
export function PointRow({ block, quotes, owners, onCite }: PointRowProps) {
  const { owner, rest } = owners ? splitOwner(block.text) : { owner: null, rest: block.text };
  const seen = new Set<string>();
  const times = block.citations.filter((c) => {
    if (seen.has(c.utterance_id)) return false;
    seen.add(c.utterance_id);
    return true;
  });
  return (
    <li className="sheet-row point-row">
      <p className="sheet-point">
        {owner ? (
          <>
            <b className="font-bold">{owner}:</b> {rest}
          </>
        ) : (
          rest
        )}
      </p>
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
          <p key={line.id} className="quote">
            <span className={cn("caps mr-1.5 text-[14px]", line.channel === 0 ? "text-you" : "text-them")}>
              {line.speaker}
            </span>
            <q>{line.text}</q>
          </p>
        ))}
      </div>
    </li>
  );
}
