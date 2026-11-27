import { useMemo } from "react";
import type { ItemStatus, Note, NoteFailureReason, Utterance } from "@/bridge";
import { PointRow } from "@/components/PointRow";
import { noteQuotes } from "@/note";
import { canRetry, noteFailureText, strings } from "@/strings";
import type { NoteStatus } from "@/useEvra";

interface NoteViewProps {
  note: Note | null;
  utterances: Utterance[];
  status: NoteStatus | undefined;
  canWrite: boolean;
  onWrite: () => void;
  onCite: (utteranceId: string) => void;
  onItemStatus: (itemId: string, status: ItemStatus) => void;
}

// The note is a sheet: point | timed centre rule | the lines it came from. It folds to
// rule | point over quotes when narrow. The note appears once, complete (D16): while one is
// written, only its progress shows, as a band on the sheet.
export function NoteView({ note, utterances, status, canWrite, onWrite, onCite, onItemStatus }: NoteViewProps) {
  const byId = useMemo(() => new Map(utterances.map((u) => [u.id, u])), [utterances]);
  const failed = status?.failed;
  return (
    <div className="h-full overflow-y-auto px-[var(--gutter)] pb-12">
      <div className="sheet measure -mx-2.5 pt-3">
        {status?.stage ? (
          <WritingRow label={strings.stages(status.stage) ?? strings.writingNote} />
        ) : (
          <>
            {failed && (
              <FailureRow
                reason={failed.reason}
                model={failed.model}
                onRetry={canWrite && canRetry(failed.reason) ? onWrite : undefined}
              />
            )}
            {note ? (
              <Sheet note={note} byId={byId} onCite={onCite} onItemStatus={onItemStatus} />
            ) : (
              !failed && (
                <div className="px-2.5 pt-5">
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
          </>
        )}
      </div>
    </div>
  );
}

function WritingRow({ label }: { label: string }) {
  return (
    <div role="status" className="sheet-row bg-band">
      <div className="sheet-point py-3.5">
        <p className="caps text-[15px] leading-[18px] text-rule-ink">{label}</p>
        <p className="mt-1.5">{strings.writingNoteDetail}</p>
      </div>
      <span aria-hidden="true" className="sheet-mid progress-mid">
        <span />
      </span>
    </div>
  );
}

function FailureRow({ reason, model, onRetry }: { reason: NoteFailureReason; model?: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="sheet-row bg-band-deep">
      <div className="sheet-point py-3.5">
        <p className="caps text-[15px] leading-[18px] text-rule-ink">{strings.noteNotWritten}</p>
        <p className="mt-1.5">{noteFailureText(reason, model)}</p>
      </div>
      <span className="sheet-mid on-rule" />
      <div className="sheet-quotes py-3.5">
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="rounded-lg bg-ink px-3 py-1 font-semibold text-pad transition-colors hover:bg-ink/88"
          >
            {strings.retry}
          </button>
        )}
      </div>
    </div>
  );
}

interface SheetProps {
  note: Note;
  byId: Map<string, Utterance>;
  onCite: (id: string) => void;
  onItemStatus: (itemId: string, status: ItemStatus) => void;
}

function Sheet({ note, byId, onCite, onItemStatus }: SheetProps) {
  return (
    <article>
      <div aria-hidden="true" className="sheet-row sheet-heads">
        <span className="sheet-point" />
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
                  onItemStatus={onItemStatus}
                />
              ))}
            </ul>
          </section>
        ))}
    </article>
  );
}
