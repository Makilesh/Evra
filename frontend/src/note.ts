// What the note sheet and "Copy as Markdown" need from a note.
import type { Note, NoteBlock, Utterance } from "@/bridge";
import { formatClock } from "@/format";

/** The transcript lines a point cites, in citation order; unknown ids are skipped, repeats shown once. */
export function noteQuotes(block: NoteBlock, byId: Map<string, Utterance>): Utterance[] {
  const seen = new Set<string>();
  const quotes: Utterance[] = [];
  for (const citation of block.citations) {
    const line = byId.get(citation.utterance_id);
    if (!line || seen.has(line.id)) continue;
    seen.add(line.id);
    quotes.push(line);
  }
  return quotes;
}

/** Every point the note kept passed the check against the transcript (§7.5). */
export function pointCount(note: Note): number {
  return note.sections.reduce((sum, section) => sum + section.blocks.length, 0);
}

export function noteToMarkdown(title: string, line: string, note: Note): string {
  const out = [`# ${title}`, line];
  for (const section of note.sections) {
    if (section.blocks.length === 0) continue;
    out.push("", `## ${section.title}`);
    for (const block of section.blocks) {
      const ids = new Set<string>();
      const times: string[] = [];
      for (const citation of block.citations) {
        if (ids.has(citation.utterance_id)) continue;
        ids.add(citation.utterance_id);
        times.push(formatClock(citation.start_ms));
      }
      out.push(`- ${block.text}${times.length > 0 ? ` (${times.join(", ")})` : ""}`);
    }
  }
  return `${out.join("\n")}\n`;
}

const OWNER = /^([^\s:]{1,24}):\s+([\s\S]*)$/;

/** Action items start with their owner ("You: send …"), which the sheet sets in bold. */
export function splitOwner(text: string): { owner: string | null; rest: string } {
  const match = OWNER.exec(text);
  return match ? { owner: match[1], rest: match[2] } : { owner: null, rest: text };
}
