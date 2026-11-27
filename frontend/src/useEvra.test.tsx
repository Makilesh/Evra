import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import {
  emit,
  setApiForTests,
  type AskRefusal,
  type ItemStatus,
  type MeetingDetail,
  type MeetingSummary,
  type NoteLine,
  type Question,
} from "@/bridge";
import { DETAIL, MEETING, makeFakeApi } from "@/test/fakeApi";
import { useEvra } from "@/useEvra";

afterEach(() => {
  vi.useRealTimers();
  setApiForTests(null);
});

const LIVE: MeetingSummary = {
  ...MEETING,
  id: "m2",
  title: "Recording 2026-09-28 13:51",
  state: "recording",
  has_note: false,
  duration_ms: null,
};
const LIVE_DETAIL: MeetingDetail = { meeting: LIVE, utterances: [], note: null, questions: [], notes: [], with: null };

it("loads the meetings and opens the newest one", async () => {
  setApiForTests(makeFakeApi());
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).toEqual(DETAIL));
  expect(result.current.state.appName).toBe("Evra");
  expect(result.current.state.meetings).toEqual([MEETING]);
  expect(result.current.state.selectedId).toBe("m1");
});

it("appends live lines only for the open meeting, once each", async () => {
  setApiForTests(makeFakeApi());
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).not.toBeNull());
  const line = { meeting_id: "m1", id: "x1", channel: 0, speaker: "You", start_ms: 200_000, end_ms: 201_000, text: "New line." };
  act(() => {
    emit("transcript.utterance", line);
    emit("transcript.utterance", line);
    emit("transcript.utterance", { ...line, meeting_id: "other", id: "x2" });
  });
  expect(result.current.state.detail?.utterances.map((u) => u.id)).toEqual(["u1", "u2", "x1"]);
});

it("picks up a recording in progress after the window reloads", async () => {
  setApiForTests(
    makeFakeApi({
      recording_state: async () => ({ state: "recording", meeting_id: "m2", started_at: 5 }),
      list_meetings: async () => [LIVE, MEETING],
      get_meeting: async (id) => (id === "m2" ? LIVE_DETAIL : DETAIL),
    }),
  );
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail?.meeting.id).toBe("m2"));
  expect(result.current.state.recording.state).toBe("recording");
});

it("opens a meeting when its recording starts", async () => {
  let meetings = [MEETING];
  setApiForTests(
    makeFakeApi({
      list_meetings: async () => meetings,
      get_meeting: async (id) => (id === "m2" ? LIVE_DETAIL : DETAIL),
    }),
  );
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.selectedId).toBe("m1"));
  meetings = [LIVE, MEETING];
  act(() => emit("recording.state", { state: "recording", meeting_id: "m2", started_at: 5 }));
  await waitFor(() => expect(result.current.state.detail?.meeting.id).toBe("m2"));
  await waitFor(() => expect(result.current.state.meetings).toHaveLength(2));
});

it("tracks note progress and failure per meeting, and clears them when the note is ready", async () => {
  setApiForTests(makeFakeApi());
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.ready).toBe(true));
  act(() => emit("note.stage", { meeting_id: "m1", stage: "writing" }));
  expect(result.current.state.noteStatus.m1).toEqual({ stage: "writing" });
  act(() => emit("note.failed", { meeting_id: "m1", reason: "model_missing", model: "gemma4:12b" }));
  expect(result.current.state.noteStatus.m1).toEqual({ failed: { reason: "model_missing", model: "gemma4:12b" } });
  act(() => emit("note.ready", { meeting_id: "m1" }));
  expect(result.current.state.noteStatus.m1).toBeUndefined();
});

it("takes a meeting's new name from Python, in the list and the open meeting", async () => {
  setApiForTests(makeFakeApi());
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).toEqual(DETAIL));
  act(() => emit("meeting.renamed", { meeting_id: "m1", title: "Launch date and designer proposal" }));
  expect(result.current.state.meetings.map((m) => m.title)).toEqual(["Launch date and designer proposal"]);
  expect(result.current.state.detail?.meeting.title).toBe("Launch date and designer proposal");
  act(() => emit("meeting.renamed", { meeting_id: "other", title: "Elsewhere" }));
  expect(result.current.state.meetings.map((m) => m.title)).toEqual(["Launch date and designer proposal"]);
  expect(result.current.state.detail?.meeting.title).toBe("Launch date and designer proposal");
});

it("keeps capture hints from the finished recording", async () => {
  setApiForTests(makeFakeApi());
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.ready).toBe(true));
  act(() =>
    emit("recording.finished", { meeting_id: "m1", utterances: 2, failed_segments: 0, hints: ["No system audio arrived."] }),
  );
  expect(result.current.state.hints.m1).toEqual(["No system audio arrived."]);
});

it("reports why recording could not start, but not a busy reply", async () => {
  const replies = [
    { ok: false, error: "microphone 'Headset' is not connected", hint: "Pick it again." },
    { ok: false, reason: "busy" },
  ];
  setApiForTests(makeFakeApi({ start_recording: async () => replies.shift()! }));
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.ready).toBe(true));
  await act(() => result.current.startRecording("Headset"));
  expect(result.current.state.startError).toEqual({ error: "microphone 'Headset' is not connected", hint: "Pick it again." });
  await act(() => result.current.startRecording("Headset"));
  expect(result.current.state.startError).toBeNull();
});

it("says so when the bridge is unavailable", async () => {
  setApiForTests(makeFakeApi({ app_info: async () => { throw new Error("boom"); } }));
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.bridgeError).toBe("boom"));
});

it("lists the microphones again on request", async () => {
  const mics = [
    { default: "Array", mics: ["Array"], chosen: "" },
    { default: "Array", mics: ["Array", "Headset (Mivi Roam 2)"], chosen: "" },
  ];
  setApiForTests(makeFakeApi({ list_mics: async () => mics.shift()! }));
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.mics?.mics).toEqual(["Array"]));
  await act(() => result.current.refreshMics());
  expect(result.current.state.mics?.mics).toEqual(["Array", "Headset (Mivi Roam 2)"]);
});

const ASKING: Question = { id: "q1", text: "What did I promise?", asked_at: 1, state: "asking", points: [], excerpt: false };
const ANSWERED: Question = {
  ...ASKING,
  state: "answered",
  points: [{ text: "You'll send the proposal by Thursday.", citations: [{ utterance_id: "u2", start_ms: 110_000 }] }],
  model: "gemma4:12b",
};

it("ask appends the question and the event updates it", async () => {
  const api = makeFakeApi({ ask_meeting: vi.fn(async () => ({ ok: true, question: ASKING })) });
  setApiForTests(api);
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).toEqual(DETAIL));
  let refusal: AskRefusal | null = "busy";
  await act(async () => {
    refusal = await result.current.ask("m1", "What did I promise?");
  });
  expect(refusal).toBeNull();
  expect(api.ask_meeting).toHaveBeenCalledWith("m1", "What did I promise?");
  expect(result.current.state.detail?.questions).toEqual([ASKING]);
  act(() => emit("question.updated", { meeting_id: "other", question: { ...ANSWERED, id: "q9" } }));
  expect(result.current.state.detail?.questions).toEqual([ASKING]);
  act(() => emit("question.updated", { meeting_id: "m1", question: ANSWERED }));
  expect(result.current.state.detail?.questions).toEqual([ANSWERED]);
});

it("ask returns the refusal, and busy when the bridge fails", async () => {
  const replies = [
    async () => ({ ok: false, reason: "recording" as const }),
    async () => {
      throw new Error("bridge gone");
    },
  ];
  setApiForTests(makeFakeApi({ ask_meeting: vi.fn(() => replies.shift()!()) }));
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).not.toBeNull());
  await act(async () => expect(await result.current.ask("m1", "When is it due?")).toBe("recording"));
  await act(async () => expect(await result.current.ask("m1", "When is it due?")).toBe("busy"));
  expect(result.current.state.detail?.questions).toEqual([]);
});

it("keeps an answer that arrives before the reply to the question", async () => {
  setApiForTests(
    makeFakeApi({
      ask_meeting: vi.fn(async () => {
        emit("question.updated", { meeting_id: "m1", question: ANSWERED });
        return { ok: true, question: ASKING };
      }),
    }),
  );
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).not.toBeNull());
  await act(async () => {
    await result.current.ask("m1", "What did I promise?");
  });
  expect(result.current.state.detail?.questions).toEqual([ANSWERED]);
});

/** get_meeting answers DETAIL at once the first `quick` times, then waits for `release`. */
function slowReload(quick: number) {
  let calls = 0;
  const reload = { release: (_detail: MeetingDetail) => {} };
  const get_meeting = vi.fn(() =>
    calls++ < quick
      ? Promise.resolve(DETAIL)
      : new Promise<MeetingDetail | null>((resolve) => {
          reload.release = resolve;
        }),
  );
  return { get_meeting, reload };
}

it("keeps an answer when a slower reload of the meeting lands after it", async () => {
  const { get_meeting, reload } = slowReload(1);
  setApiForTests(makeFakeApi({ get_meeting }));
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).toEqual(DETAIL));
  act(() => result.current.select("m1")); // read before the answer was stored
  await waitFor(() => expect(get_meeting).toHaveBeenCalledTimes(2));
  act(() => emit("question.updated", { meeting_id: "m1", question: ANSWERED }));
  expect(result.current.state.detail?.questions).toEqual([ANSWERED]);
  await act(async () => reload.release({ ...DETAIL, questions: [ASKING] }));
  expect(result.current.state.detail?.questions).toEqual([ANSWERED]);
});

it("keeps an answer that arrives while its meeting is still loading", async () => {
  const { get_meeting, reload } = slowReload(0);
  setApiForTests(makeFakeApi({ get_meeting }));
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(get_meeting).toHaveBeenCalledTimes(1));
  expect(result.current.state.selectedId).toBe("m1");
  expect(result.current.state.detail).toBeNull();
  act(() => emit("question.updated", { meeting_id: "m1", question: ANSWERED }));
  await act(async () => reload.release({ ...DETAIL, questions: [] }));
  expect(result.current.state.detail?.questions).toEqual([ANSWERED]);
});

it("keeps a question just asked when a reload read the meeting before it", async () => {
  const { get_meeting, reload } = slowReload(1);
  setApiForTests(makeFakeApi({ get_meeting, ask_meeting: vi.fn(async () => ({ ok: true, question: ASKING })) }));
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).toEqual(DETAIL));
  act(() => result.current.select("m1"));
  await waitFor(() => expect(get_meeting).toHaveBeenCalledTimes(2));
  await act(async () => {
    await result.current.ask("m1", "What did I promise?");
  });
  await act(async () => reload.release({ ...DETAIL, questions: [] }));
  expect(result.current.state.detail?.questions).toEqual([ASKING]);
});

const WITH_ITEM: MeetingDetail = {
  ...DETAIL,
  note: {
    model: "gemma4:12b",
    sections: [
      {
        id: "action_items",
        title: "Action items",
        blocks: [
          {
            text: "You: Send the proposal (by Thursday)",
            citations: [{ utterance_id: "u2", start_ms: 110_000 }],
            item: { id: "i1", kind: "action_item", status: "open", owner: "You", due: "by Thursday" },
          },
        ],
      },
    ],
  },
};

function itemStatus(detail: MeetingDetail | null): string | undefined {
  return detail?.note?.sections[0].blocks[0].item?.status;
}

it("ticks an item at once and puts it back when Python refuses", async () => {
  const replies: ((value: { ok: boolean }) => void)[] = [];
  const set_item_status = vi.fn(() => new Promise<{ ok: boolean }>((resolve) => replies.push(resolve)));
  setApiForTests(makeFakeApi({ get_meeting: async () => WITH_ITEM, set_item_status }));
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).toEqual(WITH_ITEM));

  let saved: Promise<boolean> = Promise.resolve(false);
  act(() => {
    saved = result.current.setItemStatus("i1", "done");
  });
  expect(itemStatus(result.current.state.detail)).toBe("done"); // before Python answers
  await waitFor(() => expect(set_item_status).toHaveBeenCalledWith("i1", "done"));
  await act(async () => {
    replies[0]({ ok: true });
    expect(await saved).toBe(true);
  });
  expect(itemStatus(result.current.state.detail)).toBe("done");

  act(() => {
    saved = result.current.setItemStatus("i1", "open");
  });
  expect(itemStatus(result.current.state.detail)).toBe("open");
  await waitFor(() => expect(replies).toHaveLength(2));
  await act(async () => {
    replies[1]({ ok: false });
    expect(await saved).toBe(false);
  });
  expect(itemStatus(result.current.state.detail)).toBe("done"); // put back: it wasn't saved
});

it("asks Python to read the meeting ahead, ignoring the reply and errors", async () => {
  const api = makeFakeApi({
    prepare_ask: vi.fn(async () => {
      throw new Error("not now");
    }),
  });
  setApiForTests(api);
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.ready).toBe(true));
  act(() => result.current.prepareAsk("m1"));
  await waitFor(() => expect(api.prepare_ask).toHaveBeenCalledWith("m1"));
});

it("saves quick ticks of one item in turn and ends where Python does", async () => {
  let stored: ItemStatus = "open"; // the database
  const answers: ((ok: boolean) => void)[] = [];
  const set_item_status = vi.fn(
    (_id: string, status: ItemStatus) =>
      new Promise<{ ok: boolean }>((resolve) =>
        answers.push((ok) => {
          if (ok) stored = status;
          resolve({ ok });
        }),
      ),
  );
  setApiForTests(makeFakeApi({ get_meeting: async () => WITH_ITEM, set_item_status }));
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).toEqual(WITH_ITEM));

  const ticks: Promise<boolean>[] = [];
  act(() => {
    ticks.push(result.current.setItemStatus("i1", "done"));
    ticks.push(result.current.setItemStatus("i1", "open"));
    ticks.push(result.current.setItemStatus("i1", "done"));
  });
  expect(itemStatus(result.current.state.detail)).toBe("done"); // every tick shows at once
  await waitFor(() => expect(set_item_status).toHaveBeenCalledTimes(1));
  await act(async () => answers[0](false)); // the first fails...
  await waitFor(() => expect(set_item_status).toHaveBeenCalledTimes(2)); // ...and only then the next goes
  expect(itemStatus(result.current.state.detail)).toBe("done"); // the last tick still shows
  await act(async () => answers[1](true));
  await waitFor(() => expect(set_item_status).toHaveBeenCalledTimes(3));
  await act(async () => {
    answers[2](false);
    expect(await Promise.all(ticks)).toEqual([false, true, false]);
  });
  expect(stored).toBe("open");
  expect(itemStatus(result.current.state.detail)).toBe("open"); // the box ends where Python is
});

it("forgets an item's ticks once answered, so a later failed tick shows what Python has then", async () => {
  let stored: ItemStatus = "open"; // the database
  const replies = [true, false];
  const atStored = (): MeetingDetail => {
    const [section] = WITH_ITEM.note!.sections;
    const [block] = section.blocks;
    const item = { ...block.item!, status: stored };
    return { ...WITH_ITEM, note: { ...WITH_ITEM.note!, sections: [{ ...section, blocks: [{ ...block, item }] }] } };
  };
  const set_item_status = vi.fn(async (_id: string, status: ItemStatus) => {
    const ok = replies.shift()!;
    if (ok) stored = status;
    return { ok };
  });
  setApiForTests(makeFakeApi({ get_meeting: async () => atStored(), set_item_status }));
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(itemStatus(result.current.state.detail)).toBe("open"));
  await act(() => result.current.setItemStatus("i1", "done"));
  expect(itemStatus(result.current.state.detail)).toBe("done");
  stored = "open"; // opened again elsewhere (Plan C's Promises page ticks the same records)
  act(() => emit("note.ready", { meeting_id: "m1" })); // the meeting is read again
  await waitFor(() => expect(itemStatus(result.current.state.detail)).toBe("open"));
  await act(() => result.current.setItemStatus("i1", "done")); // not saved
  expect(itemStatus(result.current.state.detail)).toBe("open"); // Python's status, not the old "done"
});

const TYPED: NoteLine[] = [
  {
    id: "a",
    text: "Budget approved",
    captured_at: MEETING.started_at + 75_000,
    pasted: false,
    captured_ms: 75_000,
    aligned: [{ utterance_id: "u1", start_ms: 65_000 }],
  },
];
/** What reaches Python: the lines without what only the window reads. */
const SAVED = [{ id: "a", text: "Budget approved", captured_at: MEETING.started_at + 75_000, pasted: false }];
const ASK: NoteLine = { id: "b", text: "Ask Priya", captured_at: MEETING.started_at + 90_000, pasted: false };

it("saves 400 ms after typing", async () => {
  const api = makeFakeApi();
  setApiForTests(api);
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).toEqual(DETAIL));
  vi.useFakeTimers();
  act(() => result.current.editNotes("m1", TYPED));
  expect(result.current.state.notes.m1).toEqual(TYPED); // the window shows it at once
  await act(() => vi.advanceTimersByTimeAsync(300));
  act(() => result.current.editNotes("m1", [...TYPED, ASK])); // still typing: the wait starts again
  await act(() => vi.advanceTimersByTimeAsync(399));
  expect(api.save_notes).not.toHaveBeenCalled();
  await act(() => vi.advanceTimersByTimeAsync(1));
  expect(api.save_notes).toHaveBeenCalledTimes(1);
  expect(api.save_notes).toHaveBeenCalledWith("m1", [...SAVED, ASK]); // the whole pad, once
});

it("flushes notes before stop", async () => {
  const calls: string[] = [];
  let answer = (_ok: boolean) => {};
  const api = makeFakeApi({
    save_notes: vi.fn(() => {
      calls.push("save_notes");
      return new Promise<{ ok: boolean }>((resolve) => {
        answer = (ok) => resolve({ ok });
      });
    }),
    stop_recording: vi.fn(async () => {
      calls.push("stop_recording");
      return { ok: true };
    }),
  });
  setApiForTests(api);
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).toEqual(DETAIL));
  act(() => result.current.editNotes("m1", TYPED)); // typed a moment ago: not saved yet
  let stopped: Promise<void> = Promise.resolve();
  act(() => {
    stopped = result.current.stopRecording();
  });
  await waitFor(() => expect(api.save_notes).toHaveBeenCalledWith("m1", SAVED));
  expect(calls).toEqual(["save_notes"]); // Stop waits for Python's answer
  await act(async () => {
    answer(true);
    await stopped;
  });
  expect(calls).toEqual(["save_notes", "stop_recording"]);
});

it("saves the notes before a note is written again", async () => {
  const api = makeFakeApi();
  setApiForTests(api);
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).toEqual(DETAIL));
  act(() => result.current.editNotes("m1", TYPED));
  await act(() => result.current.writeNote("m1"));
  expect(api.save_notes).toHaveBeenCalledWith("m1", SAVED);
  const [saved] = vi.mocked(api.save_notes).mock.invocationCallOrder;
  const [written] = vi.mocked(api.write_note).mock.invocationCallOrder;
  expect(saved).toBeLessThan(written);
});

it("still stops when the notes can't be saved, says so, and saves them on the next change", async () => {
  const replies = [false, true];
  const api = makeFakeApi({ save_notes: vi.fn(async () => ({ ok: replies.shift()! })) });
  setApiForTests(api);
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).toEqual(DETAIL));
  act(() => result.current.editNotes("m1", TYPED));
  await act(() => result.current.stopRecording());
  expect(api.stop_recording).toHaveBeenCalled(); // the owner's Stop always works
  expect(result.current.state.notesSaveFailed).toEqual({ m1: true });
  expect(result.current.state.notes.m1).toEqual(TYPED); // the lines stay in the window
  act(() => result.current.editNotes("m1", [...TYPED, ASK]));
  await act(() => result.current.flushNotes());
  expect(api.save_notes).toHaveBeenLastCalledWith("m1", [...SAVED, ASK]);
  expect(result.current.state.notesSaveFailed).toEqual({});
});

/** save_notes answering only when the test says so, and the order of the calls Stop makes. */
function heldSaves() {
  const calls: string[] = [];
  const answers: ((ok: boolean) => void)[] = [];
  const api = makeFakeApi({
    save_notes: vi.fn((_meetingId: string, lines: { text: string }[]) => {
      calls.push(`save_notes ${lines.map((l) => l.text).join(" | ")}`);
      return new Promise<{ ok: boolean }>((resolve) => answers.push((ok) => resolve({ ok })));
    }),
    stop_recording: vi.fn(async () => {
      calls.push("stop_recording");
      return { ok: true };
    }),
  });
  return { api, calls, answers };
}

it("sends a pad whose save failed again at Stop", async () => {
  const { api, calls, answers } = heldSaves();
  setApiForTests(api);
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).toEqual(DETAIL));
  vi.useFakeTimers();
  act(() => result.current.editNotes("m1", TYPED));
  await act(() => vi.advanceTimersByTimeAsync(400)); // the debounced save goes...
  vi.useRealTimers();
  await waitFor(() => expect(answers).toHaveLength(1));
  await act(async () => answers[0](false)); // ...and fails
  expect(result.current.state.notesSaveFailed).toEqual({ m1: true });
  let stopped: Promise<void> = Promise.resolve();
  act(() => {
    stopped = result.current.stopRecording(); // with no more typing
  });
  await waitFor(() => expect(answers).toHaveLength(2)); // the pad goes again...
  await act(async () => {
    answers[1](true);
    await stopped;
  });
  expect(calls).toEqual(["save_notes Budget approved", "save_notes Budget approved", "stop_recording"]);
  expect(result.current.state.notesSaveFailed).toEqual({}); // ...before the note job reads it
});

it("sends again a save that fails while Stop waits for it, but never over a newer change", async () => {
  const { api, calls, answers } = heldSaves();
  setApiForTests(api);
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).toEqual(DETAIL));
  act(() => {
    result.current.editNotes("m1", TYPED);
    void result.current.flushNotes(); // a save on its way...
  });
  await waitFor(() => expect(answers).toHaveLength(1));
  act(() => result.current.editNotes("m1", [...TYPED, ASK])); // ...the owner types on...
  await act(async () => answers[0](false)); // ...and the older save fails: the newer pad waits
  let stopped: Promise<void> = Promise.resolve();
  act(() => {
    stopped = result.current.stopRecording();
  });
  await waitFor(() => expect(answers).toHaveLength(2));
  await act(async () => answers[1](false)); // Stop's own save fails: it still stops
  await act(() => stopped);
  expect(calls).toEqual([
    "save_notes Budget approved",
    "save_notes Budget approved | Ask Priya",
    "stop_recording",
  ]);

  act(() => {
    void result.current.flushNotes(); // the failed pad is waiting again...
  });
  await waitFor(() => expect(answers).toHaveLength(3));
  let stoppedAgain: Promise<void> = Promise.resolve();
  act(() => {
    stoppedAgain = result.current.stopRecording(); // ...and Stop comes while its save is out
  });
  await act(async () => answers[2](false));
  await waitFor(() => expect(answers).toHaveLength(4)); // so Stop sends it once more
  await act(async () => {
    answers[3](true);
    await stoppedAgain;
  });
  expect(calls.slice(3)).toEqual([
    "save_notes Budget approved | Ask Priya",
    "save_notes Budget approved | Ask Priya",
    "stop_recording",
  ]);
});

it("sends each meeting's failed pad again, though another meeting's change waits", async () => {
  const { api, calls, answers } = heldSaves();
  setApiForTests(api);
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).toEqual(DETAIL));
  act(() => {
    result.current.editNotes("m1", TYPED);
    void result.current.flushNotes(); // m1's pad on its way...
  });
  await waitFor(() => expect(answers).toHaveLength(1));
  act(() => result.current.editNotes("m3", [ASK])); // ...the owner types in another meeting's pad...
  await act(async () => answers[0](false)); // ...and m1's save fails
  expect(result.current.state.notesSaveFailed).toEqual({ m1: true });
  let stopped: Promise<void> = Promise.resolve();
  act(() => {
    stopped = result.current.stopRecording();
  });
  await waitFor(() => expect(answers).toHaveLength(2));
  await act(async () => answers[1](true));
  await waitFor(() => expect(answers).toHaveLength(3));
  await act(async () => {
    answers[2](true);
    await stopped;
  });
  const sent = vi.mocked(api.save_notes).mock.calls.map(([meetingId, lines]) => [meetingId, lines.length]);
  expect(sent).toEqual([
    ["m1", 1],
    ["m3", 1],
    ["m1", 1], // m1's pad again, under m1, before Stop
  ]);
  expect(calls.at(-1)).toBe("stop_recording");
  expect(result.current.state.notesSaveFailed).toEqual({});
});

it("saves a meeting's notes under it when another meeting opens", async () => {
  const other: MeetingSummary = { ...MEETING, id: "m3", title: "Design review" };
  const api = makeFakeApi({
    list_meetings: async () => [MEETING, other],
    get_meeting: async (id) => (id === "m3" ? { ...DETAIL, meeting: other } : DETAIL),
  });
  setApiForTests(api);
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).toEqual(DETAIL));
  act(() => result.current.editNotes("m1", TYPED));
  act(() => result.current.select("m3"));
  await waitFor(() => expect(api.save_notes).toHaveBeenCalledWith("m1", SAVED));
  await waitFor(() => expect(result.current.state.detail?.meeting.id).toBe("m3"));
  act(() => result.current.editNotes("m3", [ASK]));
  await act(() => result.current.flushNotes());
  expect(api.save_notes).toHaveBeenLastCalledWith("m3", [ASK]);
  expect(api.save_notes).toHaveBeenCalledTimes(2);
  expect(result.current.state.notes.m1).toEqual(TYPED); // kept for when it opens again
});
