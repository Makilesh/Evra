// Every user-facing string in one place (BUILD.md §8.4: one i18n layer later).
import type { AskFailureReason, AskRefusal, NoteFailureReason, Theme } from "@/bridge";

const STAGES: Record<string, string> = {
  writing: "Writing note…",
  items: "Listing action items…",
  combining: "Putting the note together…",
};

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
  shortcuts: "Shortcuts",
  searchShortcutHelp: "Search your meetings",
  meetingTabs: "Meeting",
  noteTab: "Note",
  transcriptTab: "Transcript",
  lineCount: (n: number) => `${n} ${n === 1 ? "line" : "lines"}`,
  oneOnOne: "1:1",
  renameMeeting: "Rename meeting",
  meetingTitle: "Meeting title",
  captureNotes: "Capture notes",
  whereFrom: "Where it came from",
  noteNotWritten: "Note not written",
  writtenHere: "Written on this PC",
  pointsChecked: (n: number) => `${n} ${n === 1 ? "point" : "points"} checked against the transcript`,
  copyMarkdown: "Copy as Markdown",
  copied: "Copied",
  copyFailed: "Couldn't copy",
  noTranscript: "Nothing has been transcribed yet.",
  listening: "Listening…",
  noNote: "No note yet.",
  writeNote: "Write note",
  writingNoteDetail: "The note is being written on this PC. It appears here once, complete.",
  retry: "Retry",
  dismiss: "Dismiss",
  jumpTo: (clock: string) => `Jump to ${clock} in the transcript`,
  markDone: (text: string) => `Done: ${text}`,
  /** What the note's progress band says; "part:2:6" is the second of a long call's six parts. */
  stages: (stage: string): string | undefined => {
    const part = /^part:(\d+):(\d+)$/.exec(stage);
    return part ? `Reading part ${part[1]} of ${part[2]}…` : STAGES[stage];
  },
  askTab: "Ask",
  askLabel: "Ask about this meeting",
  askPlaceholder: "Ask about this meeting…",
  askButton: "Ask",
  askIntro: "Ask anything about this call. Every answer sits beside the lines it came from.",
  askSuggestions: ["What did I promise?", "What did they promise?", "What did we decide?", "What's still open?"],
  askThinking: "Reading the meeting…",
  notDiscussed: "Not discussed in this meeting.",
  askUnchecked: "Evra found an answer but couldn't check it against the transcript, so it isn't shown.",
  askExcerpt: "This call is too long to read whole, so Evra read the parts that match your question.",
  askExcerptNothing: "This call is too long to read whole. Evra looked only at the parts that match your question.",
  askAgain: "Ask again",
  askAnswered: "Answer ready",
  askAfterRecording: "You can ask once the recording ends.",
  bridgeDown: "Evra couldn't reach its Python side. Close the window and start Evra again.",
  settings: "Settings",
  settingsShortcut: "Ctrl ,",
  closeSettings: "Close settings",
  closeHint: "Close (Esc)",
  theme: "Theme",
  themeNames: { light: "Light", dark: "Dark", system: "Match Windows" } as Record<Theme, string>,
  themeHelp: "Match Windows follows your Windows light or dark mode.",
  noteModel: "Note model",
  noteModelHelp: "The model in Ollama that writes each note, on this PC.",
  recommended: (model: string) => `${model} (recommended)`,
  findingModels: "Looking for models in Ollama…",
  ollamaQuiet: "Ollama isn't answering, so its models can't be listed. Start Ollama, then check again.",
  checkAgain: "Check again",
  modelMissing: (model: string) => `${model} isn't installed in Ollama. Run:`,
  pullCommand: (model: string) => `ollama pull ${model}`,
  meetingsFolder: "Meetings folder",
  meetingsFolderHelp: "Your meetings are kept here, and only here.",
  openFolder: "Open folder",
  folderNotOpened: "Couldn't open the folder.",
  about: "About",
  aboutHelp: "No accounts and no analytics: your meetings never leave this PC.",
  appVersion: (name: string, version: string) => `${name} ${version}`,
  settingNotSaved: "Couldn't save that change. It applies until Evra closes.",
};

export function noteFailureText(reason: NoteFailureReason, model?: string): string {
  switch (reason) {
    case "ollama_down":
      return "Ollama isn't running. Start it from the system tray (or install it from ollama.com).";
    case "model_missing":
      return `The note model isn't installed. Run: ollama pull ${model ?? ""}`.trim();
    case "cloud_model":
      return "That model runs in Ollama's cloud. Evra only uses models on this PC: choose another note model in Settings.";
    case "too_long":
      return "This meeting is too long for a note. You can still ask about it.";
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

/** Asking the same question again can't help when it needs more room or there's no transcript.
 *  A cloud model can: the owner may pick another model in Settings first. */
export function canAskAgain(reason: AskFailureReason | undefined): boolean {
  return reason !== "too_long" && reason !== "no_transcript";
}

/** The note's failure texts in answer words; Ollama's own problems read the same for both. */
export function askFailureText(reason: AskFailureReason | undefined): string {
  switch (reason) {
    case "interrupted":
      return "Evra closed before it answered. Ask again.";
    case "too_long":
      return "This question needs more room than the model's settings allow.";
    case "cut_off":
      return "The model ran out of room while answering.";
    case "invalid":
      return "The model didn't return a valid answer.";
    case "timeout":
      return "The model took too long to answer.";
    case "nothing_supported":
      return "Nothing in the answer could be checked against the transcript.";
    case "no_transcript":
      return "Nothing was transcribed, so there's nothing to ask about.";
    case "model_missing":
      return "The note model isn't installed in Ollama. Choose another in Settings, or install it with ollama pull.";
    case "ollama_down":
    case "cloud_model":
      return noteFailureText(reason);
    default:
      return "The question couldn't be answered.";
  }
}

const ASK_REFUSALS: Record<AskRefusal, string> = {
  invalid: "Type a question of up to 500 characters.",
  busy: "Evra is still answering the last question.",
  recording: strings.askAfterRecording,
  no_transcript: "There's no transcript to ask about yet.",
};

export function askRefusalText(reason: AskRefusal): string {
  return ASK_REFUSALS[reason];
}
