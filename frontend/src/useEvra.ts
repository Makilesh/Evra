// All window state (M3c spec §4): Python pushes events, this hook keeps them and offers actions.
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getApi,
  onEvent,
  type AskRefusal,
  type AskReply,
  type ItemStatus,
  type Levels,
  type MeetingDetail,
  type MeetingRenamed,
  type MeetingSummary,
  type MicList,
  type NoteFailed,
  type NoteFailureReason,
  type NoteItem,
  type NoteLine,
  type NoteModels,
  type Person,
  type Question,
  type QuestionUpdated,
  type RecordingFinished,
  type RecordingState,
  type SettingsInfo,
  type Theme,
  type Utterance,
} from "@/bridge";
import { NOTES_SAVE_MS } from "@/notepad";
import { strings } from "@/strings";
import { applyTheme } from "@/theme";
import { spokenBy, usePeople, withMeetingPerson } from "@/usePeople";

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
  settings: SettingsInfo | null;
  /** null while Ollama is being asked. */
  noteModels: NoteModels | null;
  settingsError: string;
  /** Each meeting's notepad once this window has changed it. These lines win over the meeting's
   *  own `notes`, which Python read and which may be behind the typing. */
  notes: Record<string, NoteLine[]>;
  /** The meetings whose notes the last save could not store. */
  notesSaveFailed: Record<string, true>;
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
  settings: null,
  noteModels: null,
  settingsError: "",
  notes: {},
  notesSaveFailed: {},
};

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function without<T>(map: Record<string, T>, key: string): Record<string, T> {
  const rest = { ...map };
  delete rest[key];
  return rest;
}

/** A question never goes back to "asking": a settled copy wins over an asking one. */
function later(known: Question, incoming: Question): Question {
  return known.state !== "asking" && incoming.state === "asking" ? known : incoming;
}

/** The question merged in place, or added when the list doesn't have it yet. */
function withQuestion(questions: Question[], question: Question): Question[] {
  const index = questions.findIndex((q) => q.id === question.id);
  if (index < 0) return [...questions, question];
  return questions.map((q, i) => (i === index ? later(q, question) : q));
}

/** The state with a question merged into its meeting, when that meeting is open. */
function withMeetingQuestion(s: EvraState, meetingId: string, question: Question): EvraState {
  const detail = s.detail;
  if (detail?.meeting.id !== meetingId) return s;
  return { ...s, detail: { ...detail, questions: withQuestion(detail.questions, question) } };
}

/** The open note's record with this id, in whichever section it is. */
function noteItem(detail: MeetingDetail | null, id: string): NoteItem | undefined {
  for (const section of detail?.note?.sections ?? []) {
    for (const block of section.blocks) {
      if (block.item?.id === id) return block.item;
    }
  }
  return undefined;
}

/** The meeting with one record's status changed; as it was when the record is not in its note. */
function withItemStatus(detail: MeetingDetail | null, id: string, status: ItemStatus): MeetingDetail | null {
  const note = detail?.note;
  if (!detail || !note || !noteItem(detail, id)) return detail;
  const sections = note.sections.map((section) => ({
    ...section,
    blocks: section.blocks.map((block) =>
      block.item?.id === id ? { ...block, item: { ...block.item, status } } : block,
    ),
  }));
  return { ...detail, note: { ...note, sections } };
}

/** One record's ticks: saved one after another, with the status Python last confirmed. */
interface Ticks {
  saves: Promise<void>;
  confirmed: ItemStatus;
  waiting: number;
}

type Heard = Map<string, Map<string, Question>>;

function hear(heard: Heard, meetingId: string, question: Question): void {
  const byId = heard.get(meetingId) ?? new Map<string, Question>();
  const known = byId.get(question.id);
  byId.set(question.id, known ? later(known, question) : question);
  heard.set(meetingId, byId);
}

/** A meeting as Python read it, with the questions heard of since laid over its own. */
function withHeard(detail: MeetingDetail, heard: Map<string, Question> | undefined): MeetingDetail {
  if (!heard) return detail;
  let questions = detail.questions;
  for (const question of heard.values()) questions = withQuestion(questions, question);
  return { ...detail, questions };
}

export function useEvra() {
  const [state, setState] = useState<EvraState>(INITIAL);
  const selected = useRef<string | null>(null);
  // Every question view this window has heard of (ask replies, question.updated), by meeting. A
  // reload of the meeting that read it a moment earlier must not put an answer back to
  // "asking", and an answer that lands while its meeting is still loading must not be lost.
  const heard = useRef<Heard>(new Map());
  // The open meeting as last shown, so a tick finds its record.
  const shown = useRef<MeetingDetail | null>(null);
  useEffect(() => {
    shown.current = state.detail;
  }, [state.detail]);
  const ticks = useRef(new Map<string, Ticks>());
  // Each meeting's pad that waits to be saved: its last change, or a save that failed. Saves go
  // to Python one at a time, in order, so an older pad never lands after a newer one.
  const unsaved = useRef(new Map<string, NoteLine[]>());
  const saveTimer = useRef<number | undefined>(undefined);
  const saving = useRef<Promise<void>>(Promise.resolve());

  const saveNotes = useCallback(async (meetingId: string, lines: NoteLine[]) => {
    let ok = false;
    try {
      const pad = lines.map(({ id, text, captured_at, pasted }) => ({ id, text, captured_at, pasted }));
      ok = (await (await getApi()).save_notes(meetingId, pad)).ok;
    } catch {
      // reported below
    }
    // A pad that wasn't saved waits again for the next flush (Stop, Write note, another
    // meeting) or edit, unless that meeting's newer pad waits; no timer tries again (RB62).
    if (!ok && !unsaved.current.has(meetingId)) unsaved.current.set(meetingId, lines);
    const rest = (s: EvraState) => without(s.notesSaveFailed, meetingId);
    setState((s) => ({ ...s, notesSaveFailed: ok ? rest(s) : { ...rest(s), [meetingId]: true } }));
  }, []);

  // Save every waiting pad now. It resolves once Python has answered every save so far, and
  // never rejects: a failure shows in `notesSaveFailed`. With nothing of its own to send, it
  // sends, once, what waits after the save in flight: that pad if its save failed, or newer
  // typing. So Stop never leaves a pad behind.
  const flushNotes = useCallback(async (): Promise<void> => {
    window.clearTimeout(saveTimer.current);
    const send = (): boolean => {
      const waiting = [...unsaved.current];
      unsaved.current.clear();
      for (const [meetingId, lines] of waiting) {
        saving.current = saving.current.then(() => saveNotes(meetingId, lines));
      }
      return waiting.length > 0;
    };
    const sent = send();
    await saving.current;
    if (!sent && send()) await saving.current;
  }, [saveNotes]);

  // The owner changed a meeting's pad: show it at once, save it 400 ms after the last change.
  const editNotes = useCallback(
    (meetingId: string, lines: NoteLine[]) => {
      unsaved.current.set(meetingId, lines);
      setState((s) => ({ ...s, notes: { ...s.notes, [meetingId]: lines } }));
      window.clearTimeout(saveTimer.current);
      saveTimer.current = window.setTimeout(() => void flushNotes(), NOTES_SAVE_MS);
    },
    [flushNotes],
  );

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
      if (selected.current === id) {
        setState((s) => ({ ...s, detail: detail && withHeard(detail, heard.current.get(id)) }));
      }
    } catch {
      // keep what is shown
    }
  }, []);

  // Who a 1:1 was with shows at once in the list, the header and the transcript; the meeting is
  // read again for its records' names.
  const linked = useCallback(
    (meetingId: string, person: Person | null) => {
      setState((s) => withMeetingPerson(s, meetingId, person));
      if (selected.current === meetingId) void loadDetail(meetingId);
    },
    [loadDetail],
  );
  const people = usePeople(linked); // the people list, who a 1:1 was with, renaming, the promises
  const { promiseStatus, showPromiseStatus, refreshPromises } = people;

  const select = useCallback(
    (id: string) => {
      // the lines typed in the meeting being left are saved under it now (RB42)
      if (selected.current !== id) void flushNotes();
      selected.current = id;
      setState((s) => ({ ...s, selectedId: id, detail: s.detail?.meeting.id === id ? s.detail : null }));
      void loadDetail(id);
    },
    [loadDetail, flushNotes],
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
          const line = spokenBy(utterance, detail.with);
          return { ...s, detail: { ...detail, utterances: [...detail.utterances, line] } };
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
      // The name lands in place: a rename being typed keeps its own draft (see MeetingView's Title).
      onEvent("meeting.renamed", (payload) => {
        const { meeting_id, title } = payload as MeetingRenamed;
        setState((s) => ({
          ...s,
          meetings: s.meetings.map((m) => (m.id === meeting_id ? { ...m, title } : m)),
          detail:
            s.detail?.meeting.id === meeting_id ? { ...s.detail, meeting: { ...s.detail.meeting, title } } : s.detail,
        }));
      }),
      // An answer lands. It may beat the reply to ask_meeting (a fast failure), so an unknown
      // question is added rather than dropped; a meeting still loading gets it from `heard`.
      onEvent("question.updated", (payload) => {
        const { meeting_id, question } = payload as QuestionUpdated;
        hear(heard.current, meeting_id, question);
        setState((s) => withMeetingQuestion(s, meeting_id, question));
      }),
    ];
    getApi()
      .then(async (api) => {
        const [info, recording, meetings, mics, settings] = await Promise.all([
          api.app_info(),
          api.recording_state(),
          api.list_meetings(),
          api.list_mics(),
          api.get_settings(),
        ]);
        if (!alive) return;
        applyTheme(settings.theme);
        setState((s) => ({ ...s, appName: info.name, ready: true, recording, meetings, mics, settings }));
        const first = recording.meeting_id ?? meetings[0]?.id;
        if (first) select(first);
      })
      .catch((error: unknown) => {
        if (alive) setState((s) => ({ ...s, bridgeError: message(error) }));
      });
    return () => {
      alive = false;
      offs.forEach((off) => off());
      window.clearTimeout(saveTimer.current);
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

  // The note job reads the pad as soon as the recording stops, so the last typed line is saved
  // first (RB42). A save that fails still stops: the owner's Stop always works.
  const stopRecording = useCallback(async () => {
    await flushNotes();
    await (await getApi()).stop_recording();
  }, [flushNotes]);

  // Writing the note again reads the pad too, so it is saved first, as at Stop.
  const writeNote = useCallback(
    async (id: string) => {
      setState((s) => ({ ...s, noteStatus: without(s.noteStatus, id) }));
      await flushNotes();
      await (await getApi()).write_note(id);
    },
    [flushNotes],
  );

  // One question at a time (Python refuses another while one is answered). The reply only says
  // the question was taken; its answer arrives as `question.updated`.
  const ask = useCallback(async (meetingId: string, text: string): Promise<AskRefusal | null> => {
    let reply: AskReply;
    try {
      reply = await (await getApi()).ask_meeting(meetingId, text);
    } catch {
      return "busy";
    }
    const question = reply.question;
    if (!reply.ok || !question) return reply.reason ?? "busy";
    // when its answer came first, the settled copy stays (see `later`)
    hear(heard.current, meetingId, question);
    setState((s) => withMeetingQuestion(s, meetingId, question));
    return null;
  }, []);

  const prepareAsk = useCallback((meetingId: string) => {
    getApi()
      .then((api) => api.prepare_ask(meetingId))
      .catch(() => {
        // a warm-up only: a question reports its own errors
      });
  }, []);

  const rename = useCallback(
    async (id: string, title: string) => {
      const reply = await (await getApi()).rename_meeting(id, title);
      if (reply.ok) {
        void refreshMeetings();
        void refreshPromises(); // a promise names its meeting
        if (selected.current === id) void loadDetail(id);
      }
      return reply.ok;
    },
    [refreshMeetings, refreshPromises, loadDetail],
  );

  // A tick (or untick) shows at once. One record's ticks are saved one after another, and once
  // the last is answered the box shows what Python last confirmed (RB41), so quick ticks leave
  // the window and the database agreeing. The record is the open meeting's, a promise on the
  // Promises page, or both. True when this tick was saved.
  const setItemStatus = useCallback(async (id: string, status: ItemStatus): Promise<boolean> => {
    const current = noteItem(shown.current, id)?.status ?? promiseStatus(id);
    if (current === undefined) return false;
    const tick = ticks.current.get(id) ?? { saves: Promise.resolve(), confirmed: current, waiting: 0 };
    ticks.current.set(id, tick);
    tick.waiting += 1;
    setState((s) => ({ ...s, detail: withItemStatus(s.detail, id, status) }));
    showPromiseStatus(id, status, false);
    let ok = false;
    tick.saves = tick.saves.then(async () => {
      try {
        ok = (await (await getApi()).set_item_status(id, status)).ok;
      } catch {
        // not saved: the box goes back below
      }
      if (ok) tick.confirmed = status;
    });
    await tick.saves;
    tick.waiting -= 1;
    if (tick.waiting === 0) {
      // the next run of ticks starts from the status shown then, which a reload may have changed
      ticks.current.delete(id);
      setState((s) => ({ ...s, detail: withItemStatus(s.detail, id, tick.confirmed) }));
      showPromiseStatus(id, tick.confirmed, true);
    }
    return ok;
  }, [promiseStatus, showPromiseStatus]);

  const refreshMics = useCallback(async () => {
    try {
      const mics = await (await getApi()).list_mics();
      setState((s) => ({ ...s, mics }));
    } catch {
      // keep the list that is shown
    }
  }, []);

  const dismissStartError = useCallback(() => setState((s) => ({ ...s, startError: null })), []);

  // Settings apply at once (no Save button); a change that could not be saved says so.
  const saveSetting = useCallback(async (change: Partial<SettingsInfo>, save: () => Promise<{ ok: boolean }>) => {
    setState((s) => ({ ...s, settingsError: "", settings: s.settings && { ...s.settings, ...change } }));
    let ok = false;
    try {
      ok = (await save()).ok;
    } catch {
      // reported below
    }
    if (!ok) setState((s) => ({ ...s, settingsError: strings.settingNotSaved }));
  }, []);

  const setTheme = useCallback(
    async (theme: Theme) => {
      applyTheme(theme);
      await saveSetting({ theme }, async () => (await getApi()).set_theme(theme));
    },
    [saveSetting],
  );

  const setNoteModel = useCallback(
    (model: string) => saveSetting({ note_model: model }, async () => (await getApi()).set_note_model(model)),
    [saveSetting],
  );

  const loadNoteModels = useCallback(async () => {
    setState((s) => ({ ...s, noteModels: null }));
    let noteModels: NoteModels = { ok: false, models: [] };
    try {
      noteModels = await (await getApi()).list_note_models();
    } catch {
      // shown as Ollama not answering
    }
    setState((s) => ({ ...s, noteModels }));
  }, []);

  const openDataFolder = useCallback(async () => {
    try {
      return (await (await getApi()).open_data_folder()).ok;
    } catch {
      return false;
    }
  }, []);

  return {
    state,
    ...people,
    select,
    startRecording,
    stopRecording,
    writeNote,
    ask,
    prepareAsk,
    rename,
    setItemStatus,
    editNotes,
    flushNotes,
    dismissStartError,
    refreshMics,
    setTheme,
    setNoteModel,
    loadNoteModels,
    openDataFolder,
  };
}
