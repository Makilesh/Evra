export const MAX_NAME = 80; // Python's limit on a person's name (store/people.py)

// A display title, its rename pencil and the input it becomes: a meeting's title and a person's
// name look the same edited in place (MeetingView's Title, PersonView's NameTitle). The editing
// itself is `useInlineEdit`.
export const DISPLAY_TITLE =
  "line-clamp-2 min-w-0 font-display text-[clamp(2.25rem,4.6vw,3.75rem)] leading-[0.95] font-extrabold text-balance";
export const RENAME_PENCIL =
  "mt-[0.15em] inline-flex size-8 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-band hover:text-ink";
export const TITLE_INPUT =
  "w-full rounded-lg bg-band px-2 font-display text-[clamp(2.25rem,4.6vw,3.75rem)] leading-[1.1] font-extrabold";

/** Why the name wasn't saved, in 13px muted type under the input, read out as it changes. */
export function InlineRefusal({ refusal, id }: { refusal: string; id: string }) {
  return (
    <div aria-live="polite">
      {refusal && (
        <p id={id} className="mt-1 text-[13px] leading-5 text-muted">
          {refusal}
        </p>
      )}
    </div>
  );
}
