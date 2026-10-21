// Every user-facing string in one place (BUILD.md §8.4: one i18n layer later).
import type { NoteFailureReason } from "@/bridge";

export const strings = {
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
  noMeetings: "No meetings yet. Press Record to start one.",
  noMatches: "No meetings match.",
  liveNow: "Recording",
  selectMeeting: "Select a meeting, or press Record to start one.",
  meetingTabs: "Meeting",
  noteTab: "Note",
  transcriptTab: "Transcript",
  oneOnOne: "1:1",
  renameMeeting: "Rename meeting",
  meetingTitle: "Meeting title",
  captureNotes: "Capture notes",
  noTranscript: "Nothing has been transcribed yet.",
  noNote: "No note yet.",
  writeNote: "Write note",
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
