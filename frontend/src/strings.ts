// Every user-facing string in one place (BUILD.md §8.4: one i18n layer later).
import type { NoteFailureReason } from "@/bridge";

export const strings = {
  claim: "Everything stays on this PC",
  record: "Record",
  stop: "Stop",
  loading: "Loading…",
  stopping: "Stopping…",
  writingNote: "Writing note…",
  microphone: "Microphone",
  windowsDefault: (name: string) => (name ? `Windows default (${name})` : "Windows default"),
  notConnected: (name: string) => `${name} (not connected)`,
  recordingTime: "Recording time",
  you: "You",
  them: "Them",
  meetings: "Meetings",
  searchMeetings: "Search meetings",
  searchShortcut: "Ctrl K",
  today: "Today",
  yesterday: "Yesterday",
  noMeetings: "No meetings yet.",
  noMatches: "No meetings match.",
  liveNow: "Recording",
  selectMeeting: "Select a meeting, or press Record to start one.",
  welcomeTitle: "Press Record when the call starts.",
  welcomeSteps: [
    "You and Them are transcribed live, on this PC.",
    "When you stop, the note is written here once, complete.",
    "Every point sits beside the words it came from.",
  ],
  meetingTabs: "Meeting",
  noteTab: "Note",
  transcriptTab: "Transcript",
  lineCount: (n: number) => `${n} ${n === 1 ? "line" : "lines"}`,
  oneOnOne: "1:1",
  renameMeeting: "Rename meeting",
  meetingTitle: "Meeting title",
  captureNotes: "Capture notes",
  theNote: "The note",
  whereFrom: "Where it came from",
  writtenHere: "Written on this PC",
  pointsChecked: (n: number) => `${n} ${n === 1 ? "point" : "points"} checked against the transcript`,
  copyMarkdown: "Copy as Markdown",
  copied: "Copied",
  copyFailed: "Couldn't copy",
  noTranscript: "Nothing has been transcribed yet.",
  noNote: "No note yet.",
  writeNote: "Write note",
  writingNoteDetail: "The note is being written on this PC. It appears here once, complete.",
  retry: "Retry",
  dismiss: "Dismiss",
  jumpTo: (clock: string) => `Jump to ${clock} in the transcript`,
  stages: { writing: "Writing note…" } as Record<string, string>,
  bridgeDown: "Evra couldn't reach its Python side. Close the window and start Evra again.",
};

export function noteFailureText(reason: NoteFailureReason, model?: string): string {
  switch (reason) {
    case "ollama_down":
      return "Ollama isn't running. Start it from the system tray (or install it from ollama.com).";
    case "model_missing":
      return `The note model isn't installed. Run: ollama pull ${model ?? ""}`.trim();
    case "too_long":
      return "This meeting is too long for one note pass yet.";
    case "cut_off":
      return "The model ran out of room while writing.";
    case "invalid":
      return "The model didn't return a valid note.";
    case "nothing_supported":
      return "Nothing in the note could be checked against the transcript.";
    case "timeout":
      return "The model took too long.";
    case "no_transcript":
      return "Nothing was transcribed, so there's no note to write.";
    default:
      return "The note couldn't be written.";
  }
}

export function canRetry(reason: NoteFailureReason): boolean {
  return reason !== "too_long" && reason !== "no_transcript";
}
