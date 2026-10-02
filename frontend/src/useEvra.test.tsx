import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { emit, setApiForTests, type MeetingSummary } from "@/bridge";
import { DETAIL, MEETING, makeFakeApi } from "@/test/fakeApi";
import { useEvra } from "@/useEvra";

afterEach(() => setApiForTests(null));

const LIVE: MeetingSummary = {
  ...MEETING,
  id: "m2",
  title: "Recording 2026-09-28 13:51",
  state: "recording",
  has_note: false,
  duration_ms: null,
};

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
      get_meeting: async (id) => (id === "m2" ? { meeting: LIVE, utterances: [], note: null } : DETAIL),
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
      get_meeting: async (id) => (id === "m2" ? { meeting: LIVE, utterances: [], note: null } : DETAIL),
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
