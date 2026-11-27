import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { emit, setApiForTests, type MeetingDetail, type Person } from "@/bridge";
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
