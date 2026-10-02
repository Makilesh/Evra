import type { Note } from "@/bridge";
import { Banner } from "@/components/Banner";
import { formatClock } from "@/format";
import { canRetry, noteFailureText, strings } from "@/strings";
import type { NoteStatus } from "@/useEvra";

interface NoteViewProps {
  note: Note | null;
  status: NoteStatus | undefined;
  canWrite: boolean;
  onWrite: () => void;
  onCite: (utteranceId: string) => void;
}

// The note appears once, complete (D16): while one is written, only its progress shows.
export function NoteView({ note, status, canWrite, onWrite, onCite }: NoteViewProps) {
  if (status?.stage) {
    return (
      <p role="status" className="animate-pulse p-6 text-muted-ink">
        {strings.stages[status.stage] ?? strings.writingNote}
      </p>
    );
  }
  const failed = status?.failed;
  return (
    <div className="h-full overflow-y-auto px-6 py-4">
      {failed && (
        <div className="mb-4">
          <Banner
            message={noteFailureText(failed.reason, failed.model)}
            action={canWrite && canRetry(failed.reason) ? { label: strings.retry, onClick: onWrite } : undefined}
          />
        </div>
      )}
      {note ? (
        <article className="space-y-5">
          {note.sections.map((section) => (
            <section key={section.id} aria-labelledby={`note-${section.id}`}>
              <h3 id={`note-${section.id}`} className="text-xs font-semibold uppercase tracking-wide text-muted-ink">
                {section.title}
              </h3>
              <ul className="mt-2 space-y-1.5 font-serif">
                {section.blocks.map((block, index) => (
                  <li key={index} className="leading-relaxed">
                    {block.text}
                    {block.citations.map((citation) => (
                      <button
                        key={citation.utterance_id}
                        type="button"
                        onClick={() => onCite(citation.utterance_id)}
                        aria-label={strings.jumpTo(formatClock(citation.start_ms))}
                        className="ml-1.5 rounded bg-line px-1.5 font-sans text-xs tabular-nums text-muted-ink hover:text-accent"
                      >
                        {formatClock(citation.start_ms)}
                      </button>
                    ))}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </article>
      ) : (
        !failed && (
          <div className="text-muted-ink">
            <p>{strings.noNote}</p>
            {canWrite && (
              <button type="button" onClick={onWrite} className="mt-3 rounded-md bg-accent px-3 py-1.5 text-paper">
                {strings.writeNote}
              </button>
            )}
          </div>
        )
      )}
    </div>
  );
}
