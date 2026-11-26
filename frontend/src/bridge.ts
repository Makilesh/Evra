// Python <-> React bridge (BUILD.md §4, D5; M3c spec §3.2-3.3).
// JS -> Python: window.pywebview.api.<method>(...) returns a Promise.
// Python -> JS: Python runs window.__evraEmit(name, payload).

export interface AppInfo {
  name: string;
  version: string;
}

export interface PingReply {
  reply: string;
}

export type RecordingPhase = "idle" | "loading" | "recording" | "stopping" | "processing";

export interface RecordingState {
  state: RecordingPhase;
  meeting_id?: string;
  started_at?: number | null;
}

export interface Levels {
  you: number;
  them: number;
}

export interface MeetingSummary {
  id: string;
  title: string;
  started_at: number;
  duration_ms: number | null;
  state: string;
  has_note: boolean;
}

export interface Utterance {
  id: string;
  channel: number;
  speaker: string;
  start_ms: number;
  end_ms: number;
  text: string;
}

export interface Citation {
  utterance_id: string;
  start_ms: number;
}

export type ItemKind = "action_item" | "decision" | "open_question";

/** An action item is ticked done, or dismissed; a decision or a question stays open. */
export type ItemStatus = "open" | "done" | "dismissed";

/** A record behind a point in a decisions, action items or open questions section. */
export interface NoteItem {
  id: string;
  kind: ItemKind;
  status: ItemStatus;
  owner: string | null;
  due: string | null;
}

export interface NoteBlock {
  text: string;
  citations: Citation[];
  /** Only on a point that comes from a record (action items, decisions, open questions). */
  item?: NoteItem;
}

export interface NoteSection {
  id: string;
  title: string;
  blocks: NoteBlock[];
}

export interface Note {
  model: string;
  sections: NoteSection[];
}

export interface MeetingDetail {
  meeting: MeetingSummary;
  utterances: Utterance[];
  note: Note | null;
  /** Oldest first. */
  questions: Question[];
}

export interface MicList {
  default: string;
  mics: string[];
  chosen: string;
}

export interface StartReply {
  ok: boolean;
  meeting_id?: string;
  reason?: string;
  error?: string;
  hint?: string;
}

export interface OkReply {
  ok: boolean;
}

export type NoteFailureReason =
  | "ollama_down"
  | "model_missing"
  | "cloud_model"
  | "too_long"
  | "cut_off"
  | "invalid"
  | "nothing_supported"
  | "timeout"
  | "no_transcript"
  | "llm_error";

export type QuestionState = "asking" | "answered" | "not_found" | "unchecked" | "failed";

/** A question fails for the note's reasons, or because Evra closed while answering it. */
export type AskFailureReason = NoteFailureReason | "interrupted";

/** Why Python did not take a question (nothing was stored). */
export type AskRefusal = "invalid" | "busy" | "recording" | "no_transcript";

/** A question about one meeting. Its answer is points cited like a note's. */
export interface Question {
  id: string;
  text: string;
  asked_at: number;
  state: QuestionState;
  /** Only when failed. */
  reason?: AskFailureReason;
  points: NoteBlock[];
  /** The call was too long to read whole, so only the parts matching the question were read. */
  excerpt: boolean;
  /** Only when answered. */
  model?: string;
}

export interface AskReply {
  ok: boolean;
  reason?: AskRefusal;
  /** Stored and "asking"; the answer arrives as `question.updated`. */
  question?: Question;
}

export interface QuestionUpdated {
  meeting_id: string;
  question: Question;
}

export interface RecordingFinished {
  meeting_id: string;
  utterances: number;
  failed_segments: number;
  hints: string[];
}

export interface NoteFailed {
  meeting_id: string;
  reason: NoteFailureReason;
  model?: string;
}

/** Evra named a meeting from its note (it only replaces the "Recording …" placeholder). */
export interface MeetingRenamed {
  meeting_id: string;
  title: string;
}

/** "system" is Match Windows: it follows Windows' light or dark app mode. */
export type Theme = "light" | "dark" | "system";

export interface SettingsInfo {
  theme: Theme;
  note_model: string;
  default_note_model: string;
  data_dir: string;
  version: string;
}

export interface NoteModels {
  ok: boolean;
  models: string[];
}

export interface EvraApi {
  ping(message: string): Promise<PingReply>;
  app_info(): Promise<AppInfo>;
  request_hello(): Promise<null>;
  list_meetings(): Promise<MeetingSummary[]>;
  get_meeting(meetingId: string): Promise<MeetingDetail | null>;
  list_mics(): Promise<MicList>;
  start_recording(micName: string): Promise<StartReply>;
  stop_recording(): Promise<OkReply>;
  write_note(meetingId: string): Promise<OkReply>;
  ask_meeting(meetingId: string, question: string): Promise<AskReply>;
  /** Reads the meeting into the model ahead of a question; the reply says nothing useful. */
  prepare_ask(meetingId: string): Promise<OkReply>;
  rename_meeting(meetingId: string, title: string): Promise<OkReply>;
  set_item_status(itemId: string, status: ItemStatus): Promise<OkReply>;
  recording_state(): Promise<RecordingState>;
  get_settings(): Promise<SettingsInfo>;
  set_theme(theme: Theme): Promise<OkReply>;
  set_note_model(model: string): Promise<OkReply>;
  list_note_models(): Promise<NoteModels>;
  open_data_folder(): Promise<OkReply>;
}

type Handler = (payload: unknown) => void;

declare global {
  interface Window {
    pywebview?: { api: EvraApi };
    __evraEmit?: (name: string, payload: unknown) => void;
  }
}

const handlers = new Map<string, Set<Handler>>();
let apiOverride: EvraApi | null = null;

export function setApiForTests(api: EvraApi | null): void {
  apiOverride = api;
}

// pywebview injects `window.pywebview = { api: {} }` first and fills in the methods later
// (then fires `pywebviewready`), so an api object alone does not mean it is usable.
function readyApi(): EvraApi | null {
  const api = window.pywebview?.api;
  return api && typeof api.app_info === "function" ? api : null;
}

export function getApi(timeoutMs = 10_000): Promise<EvraApi> {
  if (apiOverride) return Promise.resolve(apiOverride);
  const ready = readyApi();
  if (ready) return Promise.resolve(ready);
  return new Promise((resolve, reject) => {
    const onReady = () => {
      window.clearTimeout(timer);
      const api = readyApi();
      if (api) resolve(api);
      else reject(new Error("pywebviewready fired without an api"));
    };
    const timer = window.setTimeout(() => {
      window.removeEventListener("pywebviewready", onReady);
      reject(new Error("Python bridge not available"));
    }, timeoutMs);
    window.addEventListener("pywebviewready", onReady, { once: true });
  });
}

export function onEvent(name: string, handler: Handler): () => void {
  const set = handlers.get(name) ?? new Set<Handler>();
  handlers.set(name, set);
  set.add(handler);
  return () => {
    set.delete(handler);
  };
}

export function emit(name: string, payload: unknown): void {
  handlers.get(name)?.forEach((handler) => handler(payload));
}

window.__evraEmit = emit;
