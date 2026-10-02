// All window state (M3c spec §4): Python pushes events, this hook keeps them and offers actions.
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getApi,
  onEvent,
  type Levels,
  type MeetingDetail,
  type MeetingSummary,
  type MicList,
  type NoteFailed,
  type NoteFailureReason,
  type RecordingFinished,
  type RecordingState,
  type Utterance,
} from "@/bridge";

export interface NoteStatus {
  stage?: string;
  failed?: { reason: NoteFailureReason; model?: string };
}

export interface StartError {
  error: string;
  hint: string;
}

export interface EvraState {
  appName: string;
  ready: boolean;
  bridgeError: string;
  recording: RecordingState;
  levels: Levels;
  meetings: MeetingSummary[];
  mics: MicList | null;
  selectedId: string | null;
  detail: MeetingDetail | null;
  noteStatus: Record<string, NoteStatus>;
  hints: Record<string, string[]>;
  startError: StartError | null;
}

const QUIET: Levels = { you: 0, them: 0 };

const INITIAL: EvraState = {
  appName: "",
  ready: false,
  bridgeError: "",
  recording: { state: "idle" },
  levels: QUIET,
  meetings: [],
  mics: null,
  selectedId: null,
  detail: null,
  noteStatus: {},
  hints: {},
  startError: null,
};

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function without<T>(map: Record<string, T>, key: string): Record<string, T> {
  const rest = { ...map };
  delete rest[key];
  return rest;
}

export function useEvra() {
  const [state, setState] = useState<EvraState>(INITIAL);
  const selected = useRef<string | null>(null);

  const refreshMeetings = useCallback(async () => {
    try {
      const meetings = await (await getApi()).list_meetings();
      setState((s) => ({ ...s, meetings }));
    } catch {
      // the list stays as it was; the next event refreshes it
    }
  }, []);

  const loadDetail = useCallback(async (id: string) => {
    try {
      const detail = await (await getApi()).get_meeting(id);
      if (selected.current === id) setState((s) => ({ ...s, detail }));
    } catch {
      // keep what is shown
    }
  }, []);

  const select = useCallback(
    (id: string) => {
      selected.current = id;
      setState((s) => ({ ...s, selectedId: id, detail: s.detail?.meeting.id === id ? s.detail : null }));
      void loadDetail(id);
    },
    [loadDetail],
  );

  useEffect(() => {
    let alive = true;
    const offs = [
      onEvent("recording.state", (payload) => {
        const recording = payload as RecordingState;
        setState((s) => ({ ...s, recording, levels: recording.state === "recording" ? s.levels : QUIET }));
        if (recording.state === "recording" && recording.meeting_id && selected.current !== recording.meeting_id) {
          select(recording.meeting_id);
        }
        void refreshMeetings();
      }),
      onEvent("recording.levels", (payload) => setState((s) => ({ ...s, levels: payload as Levels }))),
      onEvent("transcript.utterance", (payload) => {
        const { meeting_id, ...utterance } = payload as Utterance & { meeting_id: string };
        setState((s) => {
          const detail = s.detail;
          if (!detail || detail.meeting.id !== meeting_id) return s;
          if (detail.utterances.some((u) => u.id === utterance.id)) return s;
          return { ...s, detail: { ...detail, utterances: [...detail.utterances, utterance] } };
        });
      }),
      onEvent("recording.finished", (payload) => {
        const finished = payload as RecordingFinished;
        setState((s) => ({ ...s, hints: { ...s.hints, [finished.meeting_id]: finished.hints } }));
        if (selected.current === finished.meeting_id) void loadDetail(finished.meeting_id);
      }),
      onEvent("note.stage", (payload) => {
        const { meeting_id, stage } = payload as { meeting_id: string; stage: string };
        setState((s) => ({ ...s, noteStatus: { ...s.noteStatus, [meeting_id]: { stage } } }));
      }),
      onEvent("note.ready", (payload) => {
        const { meeting_id } = payload as { meeting_id: string };
        setState((s) => ({ ...s, noteStatus: without(s.noteStatus, meeting_id) }));
        void refreshMeetings();
        if (selected.current === meeting_id) void loadDetail(meeting_id);
      }),
      onEvent("note.failed", (payload) => {
        const failed = payload as NoteFailed;
        setState((s) => ({
          ...s,
          noteStatus: { ...s.noteStatus, [failed.meeting_id]: { failed: { reason: failed.reason, model: failed.model } } },
        }));
      }),
    ];
    getApi()
      .then(async (api) => {
        const [info, recording, meetings, mics] = await Promise.all([
          api.app_info(),
          api.recording_state(),
          api.list_meetings(),
          api.list_mics(),
        ]);
        if (!alive) return;
        setState((s) => ({ ...s, appName: info.name, ready: true, recording, meetings, mics }));
        const first = recording.meeting_id ?? meetings[0]?.id;
        if (first) select(first);
      })
      .catch((error: unknown) => {
        if (alive) setState((s) => ({ ...s, bridgeError: message(error) }));
      });
    return () => {
      alive = false;
      offs.forEach((off) => off());
    };
  }, [select, refreshMeetings, loadDetail]);

  const startRecording = useCallback(async (mic: string) => {
    setState((s) => ({ ...s, startError: null }));
    try {
      const reply = await (await getApi()).start_recording(mic);
      if (!reply.ok && reply.error) {
        const startError = { error: reply.error, hint: reply.hint ?? "" };
        setState((s) => ({ ...s, startError }));
      }
    } catch (error) {
      setState((s) => ({ ...s, startError: { error: message(error), hint: "" } }));
    }
  }, []);

  const stopRecording = useCallback(async () => {
    await (await getApi()).stop_recording();
  }, []);

  const writeNote = useCallback(async (id: string) => {
    setState((s) => ({ ...s, noteStatus: without(s.noteStatus, id) }));
    await (await getApi()).write_note(id);
  }, []);

  const rename = useCallback(
    async (id: string, title: string) => {
      const reply = await (await getApi()).rename_meeting(id, title);
      if (reply.ok) {
        void refreshMeetings();
        if (selected.current === id) void loadDetail(id);
      }
      return reply.ok;
    },
    [refreshMeetings, loadDetail],
  );

  const refreshMics = useCallback(async () => {
    try {
      const mics = await (await getApi()).list_mics();
      setState((s) => ({ ...s, mics }));
    } catch {
      // keep the list that is shown
    }
  }, []);

  const dismissStartError = useCallback(() => setState((s) => ({ ...s, startError: null })), []);

  return { state, select, startRecording, stopRecording, writeNote, rename, dismissStartError, refreshMics };
}
