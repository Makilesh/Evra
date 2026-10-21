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

export interface NoteBlock {
  text: string;
  citations: Citation[];
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
  | "too_long"
  | "cut_off"
  | "invalid"
  | "nothing_supported"
  | "timeout"
  | "no_transcript"
  | "llm_error";

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
  rename_meeting(meetingId: string, title: string): Promise<OkReply>;
  recording_state(): Promise<RecordingState>;
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
