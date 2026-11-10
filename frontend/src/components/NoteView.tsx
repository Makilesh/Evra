import { useMemo } from "react";
import type { Note, NoteBlock, Utterance } from "@/bridge";
import { Banner } from "@/components/Banner";
import { formatClock } from "@/format";
import { cn } from "@/lib/utils";
import { noteQuotes, splitOwner } from "@/note";
import { canRetry, noteFailureText, strings } from "@/strings";
import type { NoteStatus } from "@/useEvra";

interface NoteViewProps {
  note: Note | null;
  utterances: Utterance[];
  status: NoteStatus | undefined;
  canWrite: boolean;
  onWrite: () => void;
  onCite: (utteranceId: string) => void;
}

// The note appears once, complete (D16): while one is written, only its progress shows.
export function NoteView({ note, utterances, status, canWrite, onWrite, onCite }: NoteViewProps) {
  const byId = useMemo(() => new Map(utterances.map((u) => [u.id, u])), [utterances]);
  if (status?.stage) {
    return (
      <div role="status" className="px-[var(--gutter)] pt-8">
        <p className="caps text-[28px] leading-8 text-rule">{strings.stages[status.stage] ?? strings.writingNote}</p>
        <p className="mt-2 max-w-[52ch] text-muted">{strings.writingNoteDetail}</p>
        <div aria-hidden="true" className="progress-rule mt-6 max-w-[36rem]">
          <span />
        </div>
      </div>
    );
  }
  const failed = status?.failed;
  return (
    <div className="h-full overflow-y-auto px-[var(--gutter)] pb-12">
      {failed && (
        <div className="max-w-[44rem] pt-5">
          <Banner
            message={noteFailureText(failed.reason, failed.model)}
            action={canWrite && canRetry(failed.reason) ? { label: strings.retry, onClick: onWrite } : undefined}
          />
        </div>
      )}
      {note ? (
        <Sheet note={note} byId={byId} onCite={onCite} />
      ) : (
        !failed && (
          <div className="pt-8">
            <p className="text-muted">{strings.noNote}</p>
            {canWrite && (
              <button
                type="button"
                onClick={onWrite}
                className="mt-3 rounded-lg bg-ink px-4 py-2 font-semibold text-pad transition-colors hover:bg-ink/88"
              >
                {strings.writeNote}
              </button>
            )}
          </div>
        )
      )}
    </div>
  );
}

// Point | timed centre rule | the lines it came from. Folds to rule | point over quotes when narrow.
function Sheet({ note, byId, onCite }: { note: Note; byId: Map<string, Utterance>; onCite: (id: string) => void }) {
  return (
    <article className="sheet -mx-2.5 pt-1">
      <div aria-hidden="true" className="sheet-row sheet-heads">
        <span className="sheet-point caps pt-3.5 text-[14px] text-muted">{strings.theNote}</span>
        <span className="sheet-mid on-rule" />
        <span className="sheet-quotes caps pt-3.5 text-[14px] text-muted">{strings.whereFrom}</span>
      </div>
      {note.sections
        .filter((section) => section.blocks.length > 0)
        .map((section) => (
          <section key={section.id} aria-labelledby={`note-${section.id}`}>
            <div className="sheet-row">
              <h2 id={`note-${section.id}`} className="sheet-point caps pt-[18px] pb-1 text-[15px] leading-[18px] text-rule">
                {section.title}
              </h2>
              <span className="sheet-mid on-rule pt-[22px]">
                <span className="detent" />
              </span>
            </div>
            <ul>
              {section.blocks.map((block, index) => (
                <PointRow
                  key={index}
                  block={block}
                  quotes={noteQuotes(block, byId)}
                  owners={section.id.includes("action")}
                  onCite={onCite}
                />
              ))}
            </ul>
          </section>
        ))}
    </article>
  );
}

interface PointRowProps {
  block: NoteBlock;
  quotes: Utterance[];
  owners: boolean;
  onCite: (id: string) => void;
}

function PointRow({ block, quotes, owners, onCite }: PointRowProps) {
  const { owner, rest } = owners ? splitOwner(block.text) : { owner: null, rest: block.text };
  const seen = new Set<string>();
  const times = block.citations.filter((c) => !seen.has(c.utterance_id) && seen.add(c.utterance_id));
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
