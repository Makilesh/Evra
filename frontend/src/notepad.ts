// What My notes needs from the owner's typed lines (BUILD.md §7.1).
import type { MeetingSummary, NoteLine, Utterance } from "@/bridge";

/** Python refuses a whole pad past these (store/notepad.py), so the window never sends one (RB57). */
export const MAX_LINES = 2000;
export const MAX_LINE_CHARS = 4000;
/** A paste longer than this is context: kept with the notes, never linked to a moment. */
export const CONTEXT_CHARS = 500;
/** The pad is saved this long after the owner's last change. */
export const NOTES_SAVE_MS = 400;

/** A new, empty line. Its id is the window's own (letters, digits and hyphens). */
export function newLine(): NoteLine {
  return { id: crypto.randomUUID(), text: "", captured_at: null, pasted: false };
}

/** The line with new text. It is stamped the first time it gets more than spaces, and keeps that
 *  time through every later edit, even one that empties it. */
export function withText(line: NoteLine, text: string, now: number): NoteLine {
  return { ...line, text, captured_at: line.captured_at ?? (text.trim() ? now : null) };
}

/** The line with text the owner typed or pasted just now. */
export function typedNow(line: NoteLine, text: string): NoteLine {
  return withText(line, text, Date.now());
}

/** When the line was typed, in ms into the call; null for an untimed line or one typed before or
 *  after the call, which has no place on its timeline. */
export function typedAt(line: NoteLine, meeting: MeetingSummary): number | null {
  if (line.captured_at === null) return null;
  const ms = line.captured_ms ?? line.captured_at - meeting.started_at;
  const ended = meeting.duration_ms;
  return ms >= 0 && (ended === null || ms < ended) ? ms : null;
}

/** The transcript line being said at `ms` into the call: the last one started by then, else the
 *  first. */
export function lineAt(utterances: Utterance[], ms: number): Utterance | undefined {
  return utterances.findLast((u) => u.start_ms <= ms) ?? utterances[0];
}

/** The pad as this window has it (its own lines win: Python's copy may lag behind the typing),
 *  with the links Python found since, by line id. */
export function padLines(local: NoteLine[] | undefined, stored: NoteLine[]): NoteLine[] {
  if (!local) return stored;
  const links = new Map(stored.map((line) => [line.id, line.aligned]));
  return local.map((line) => {
    const aligned = links.get(line.id);
    return links.has(line.id) && aligned !== line.aligned ? { ...line, aligned } : line;
  });
}

function isHighSurrogate(code: number): boolean {
  return code >= 0xd800 && code <= 0xdbff;
}

/** A text cut into pieces of at most `limit` characters (RB57): each at its last line break that
 *  fits, else its last space, else at the limit (never inside a character). The spaces and breaks
 *  at a cut are dropped, and so are pieces left blank. */
export function splitText(text: string, limit = MAX_LINE_CHARS): string[] {
  const pieces: string[] = [];
  let rest = text;
  while (rest.length > limit) {
    const fits = rest.slice(0, limit + 1); // a break right after the limit still ends a piece
    let cut = fits.lastIndexOf("\n");
    if (cut <= 0) cut = fits.lastIndexOf(" ");
    if (cut > 0) {
      pieces.push(rest.slice(0, cut).trimEnd());
      rest = rest.slice(cut + 1).trimStart();
    } else {
      cut = limit > 1 && isHighSurrogate(rest.charCodeAt(limit - 1)) ? limit - 1 : limit;
      pieces.push(rest.slice(0, cut));
      rest = rest.slice(cut);
    }
  }
  pieces.push(rest);
  const kept = pieces.filter((piece) => piece.trim() !== "");
  return kept.length > 0 ? kept : [""];
}
