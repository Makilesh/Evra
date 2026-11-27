import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { emit, setApiForTests, type MeetingDetail, type OpenPromise, type Person, type PromiseLists } from "@/bridge";
import { DETAIL, MEETING, makeFakeApi } from "@/test/fakeApi";
import { useEvra } from "@/useEvra";
import { spokenBy, withMeetingPerson } from "@/usePeople";

afterEach(() => {
  setApiForTests(null);
});

const PRIYA: Person = { id: "p1", name: "Priya" };

/** A bridge that keeps who m1 was with, and labels its lines as Python does. */
function linkingApi(overrides: Parameters<typeof makeFakeApi>[0] = {}) {
  let person: Person | null = null;
  const detail = (): MeetingDetail => ({
    ...DETAIL,
    meeting: { ...MEETING, with_name: person?.name ?? null },
    utterances: DETAIL.utterances.map((u) => (u.channel === 1 ? { ...u, speaker: person?.name ?? "Them" } : u)),
    with: person,
  });
  return makeFakeApi({
    list_meetings: vi.fn(async () => [detail().meeting]),
    get_meeting: vi.fn(async () => detail()),
    list_people: vi.fn(async () => (person ? [person] : [])),
    set_meeting_person: vi.fn(async (_meetingId: string, name: string | null) => {
      person = name ? { ...PRIYA, name } : null;
      return { ok: true, with: person };
    }),
    ...overrides,
  });
}

it("lists the people for the 'with' suggestions", async () => {
  setApiForTests(makeFakeApi({ list_people: vi.fn(async () => [PRIYA]) }));
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.people).toEqual([PRIYA]));
});

it("names them at once in the list, the open meeting's header and its transcript", () => {
  const other = { ...MEETING, id: "m2" };
  const before = { meetings: [MEETING, other], detail: DETAIL, notes: {} };
  const after = withMeetingPerson(before, "m1", PRIYA);
  expect(after.meetings.map((m) => m.with_name)).toEqual(["Priya", null]);
  expect(after.detail?.with).toEqual(PRIYA);
  expect(after.detail?.meeting.with_name).toBe("Priya");
  expect(after.detail?.utterances.map((u) => u.speaker)).toEqual(["Priya", "You"]);
  expect(after.notes).toBe(before.notes); // the rest of the state stays as it was
  expect(withMeetingPerson(after, "m1", null).detail?.utterances.map((u) => u.speaker)).toEqual(["Them", "You"]);
  // another meeting's change leaves the open one alone
  expect(withMeetingPerson(before, "m2", PRIYA).detail).toBe(DETAIL);
  const mine = DETAIL.utterances[1];
  expect(spokenBy(mine, PRIYA)).toBe(mine);
});

it("says who a 1:1 was with, and a live line from them names them", async () => {
  const api = linkingApi();
  setApiForTests(api);
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).not.toBeNull());
  let refused: string | null = "not yet";
  await act(async () => {
    refused = await result.current.setMeetingPerson("m1", "Priya");
  });
  expect(refused).toBeNull();
  expect(api.set_meeting_person).toHaveBeenCalledWith("m1", "Priya");
  await waitFor(() => expect(api.get_meeting).toHaveBeenCalledTimes(2)); // read again for the note
  expect(result.current.state.detail?.with).toEqual(PRIYA);
  expect(result.current.state.detail?.utterances.map((u) => u.speaker)).toEqual(["Priya", "You"]);
  expect(result.current.state.meetings.map((m) => m.with_name)).toEqual(["Priya"]);
  await waitFor(() => expect(result.current.people).toEqual([PRIYA]));
  // a live line from the other side names them too
  act(() => {
    emit("transcript.utterance", { meeting_id: "m1", id: "x1", channel: 1, speaker: "Them", start_ms: 200_000, end_ms: 201_000, text: "Bye." });
  });
  expect(result.current.state.detail?.utterances.at(-1)?.speaker).toBe("Priya");
  // and with no one, "Them" again
  await act(async () => {
    refused = await result.current.setMeetingPerson("m1", "");
  });
  expect(api.set_meeting_person).toHaveBeenLastCalledWith("m1", "");
  await waitFor(() => expect(result.current.state.detail?.with).toBeNull());
  expect(result.current.state.detail?.utterances.map((u) => u.speaker)).toEqual(["Them", "You"]);
  expect(result.current.state.meetings.map((m) => m.with_name)).toEqual([null]);
});

it("says why a name was refused, and changes nothing", async () => {
  const api = linkingApi({ set_meeting_person: vi.fn(async () => ({ ok: false, reason: "reserved" as const })) });
  setApiForTests(api);
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).not.toBeNull());
  let refused: string | null = null;
  await act(async () => {
    refused = await result.current.setMeetingPerson("m1", "You");
  });
  expect(refused).toBe("reserved");
  expect(result.current.state.detail?.with).toBeNull();
  setApiForTests(linkingApi({ set_meeting_person: vi.fn(async () => Promise.reject(new Error("gone"))) }));
  await act(async () => {
    refused = await result.current.setMeetingPerson("m1", "Priya");
  });
  expect(refused).toBe("failed");
});

it("renames a person, and says when someone else has the name", async () => {
  const rename_person = vi
    .fn()
    .mockResolvedValueOnce({ ok: false, reason: "taken" })
    .mockResolvedValueOnce({ ok: true });
  const list_people = vi.fn(async () => [PRIYA]);
  setApiForTests(makeFakeApi({ rename_person, list_people }));
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.people).toEqual([PRIYA]));
  let refused: string | null = null;
  await act(async () => {
    refused = await result.current.renamePerson("p1", "Sam");
  });
  expect(refused).toBe("taken");
  await act(async () => {
    refused = await result.current.renamePerson("p1", "Priya Shah");
  });
  expect(refused).toBeNull();
  expect(rename_person).toHaveBeenLastCalledWith("p1", "Priya Shah");
  await waitFor(() => expect(list_people).toHaveBeenCalledTimes(2)); // the list again, once renamed
});

/** A promise from another meeting than the one open (m1). */
const ELSEWHERE: OpenPromise = {
  id: "i9",
  text: "Book the offsite",
  due: null,
  owner: "You",
  meeting_id: "m7",
  meeting_title: "Planning",
  started_at: MEETING.started_at - 86_400_000,
  person: null,
  utterance_id: null,
  start_ms: null,
};

function promiseStatus(lists: { you: { promise: OpenPromise; status: string }[] } | null, id: string) {
  return lists?.you.find((row) => row.promise.id === id)?.status;
}

it("ticks a promise that is not in the open meeting, and puts it back when Python refuses", async () => {
  const replies = [true, false];
  const set_item_status = vi.fn(async () => ({ ok: replies.shift()! }));
  const api = makeFakeApi({ list_promises: vi.fn(async () => ({ you: [ELSEWHERE], them: [] })), set_item_status });
  setApiForTests(api);
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.promises?.you).toHaveLength(1));
  await waitFor(() => expect(result.current.state.detail).toEqual(DETAIL));
  let saved = false;
  await act(async () => {
    saved = await result.current.setItemStatus("i9", "done");
  });
  expect(saved).toBe(true);
  expect(set_item_status).toHaveBeenCalledWith("i9", "done");
  expect(promiseStatus(result.current.promises, "i9")).toBe("done");
  expect(result.current.openPromises).toBe(0);
  expect(result.current.state.detail).toEqual(DETAIL); // the open meeting is left as it was
  await act(async () => {
    saved = await result.current.setItemStatus("i9", "open"); // Undo, refused
  });
  expect(saved).toBe(false);
  expect(promiseStatus(result.current.promises, "i9")).toBe("done"); // what Python has
  await act(async () => {
    saved = await result.current.setItemStatus("nope", "done"); // neither open nor listed
  });
  expect(saved).toBe(false);
  expect(set_item_status).toHaveBeenCalledTimes(2);
});

it("keeps the newest list when two reads of the promises answer out of order", async () => {
  const answers: ((lists: PromiseLists) => void)[] = [];
  const list_promises = vi.fn(() => new Promise<PromiseLists>((resolve) => answers.push(resolve)));
  setApiForTests(makeFakeApi({ list_promises }));
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(list_promises).toHaveBeenCalledTimes(1)); // on opening
  act(() => emit("promises.changed", {}));
  await waitFor(() => expect(list_promises).toHaveBeenCalledTimes(2));
  await act(async () => answers[1]({ you: [ELSEWHERE], them: [] })); // the newer read answers first
  await act(async () => answers[0]({ you: [], them: [] }));
  expect(result.current.promises?.you.map((row) => row.promise.id)).toEqual(["i9"]);
  expect(result.current.openPromises).toBe(1);
});

it("reads the promises again when a meeting is renamed, by Evra or by the owner", async () => {
  const api = makeFakeApi();
  setApiForTests(api);
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).toEqual(DETAIL));
  await waitFor(() => expect(api.list_promises).toHaveBeenCalledTimes(1));
  act(() => emit("meeting.renamed", { meeting_id: "m1", title: "Launch date" }));
  await waitFor(() => expect(api.list_promises).toHaveBeenCalledTimes(2)); // a promise names its meeting
  await act(() => result.current.rename("m1", "Sync with Priya"));
  await waitFor(() => expect(api.list_promises).toHaveBeenCalledTimes(3));
});
