import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import App from "@/App";
import { emit, setApiForTests, type EvraApi, type ItemStatus, type MeetingSummary, type OpenPromise } from "@/bridge";
import { dayLabel } from "@/format";
import { DETAIL, MEETING, makeFakeApi } from "@/test/fakeApi";

afterEach(() => {
  vi.useRealTimers();
  setApiForTests(null);
});

const PRIYA = { id: "p1", name: "Priya" };
const DESIGN: MeetingSummary = { ...MEETING, id: "m2", title: "Design sync", started_at: new Date(2026, 8, 21, 10, 0).getTime() };
const SEND: OpenPromise = {
  id: "i1",
  text: "Send the proposal",
  due: "by Thursday",
  owner: "You",
  meeting_id: "m1",
  meeting_title: "Weekly 1:1",
  started_at: MEETING.started_at,
  person: PRIYA,
  utterance_id: "u2",
  start_ms: 110_000,
};
const DECK: OpenPromise = {
  ...SEND,
  id: "i3",
  text: "Share the deck",
  due: null,
  meeting_id: "m2",
  meeting_title: "Design sync",
  started_at: DESIGN.started_at,
  person: null,
  utterance_id: null,
  start_ms: null,
};
const MARKETING: OpenPromise = {
  ...SEND,
  id: "i2",
  text: "Tell marketing about October 14",
  due: "today",
  owner: "Them",
  utterance_id: "u1",
  start_ms: 65_000,
};

/** Python's side: the promises still open, saved statuses, and the two meetings they come from. */
function promisesApi(overrides: Partial<EvraApi> = {}): EvraApi {
  const saved = new Map<string, ItemStatus>();
  const open = (p: OpenPromise) => (saved.get(p.id) ?? "open") === "open";
  return makeFakeApi({
    list_meetings: vi.fn(async () => [MEETING, DESIGN]),
    get_meeting: vi.fn(async (id: string) => (id === "m2" ? { ...DETAIL, meeting: DESIGN } : DETAIL)),
    list_promises: vi.fn(async () => ({ you: [SEND, DECK].filter(open), them: [MARKETING].filter(open) })),
    set_item_status: vi.fn(async (id: string, status: ItemStatus) => {
      saved.set(id, status);
      return { ok: true };
    }),
    ...overrides,
  });
}

async function openPromises() {
  await userEvent.click(await screen.findByRole("button", { name: "Promises 3 open" }));
  await screen.findByRole("checkbox", { name: "Done: Send the proposal" });
}

/** Python says the promises changed (as after a saved tick), and the window reads them again. */
async function changed(api: EvraApi, listed: { you: OpenPromise[]; them: OpenPromise[] }) {
  act(() => emit("promises.changed", {}));
  await waitFor(() => expect(api.list_promises).toHaveLastResolvedWith(listed));
  await act(async () => {}); // and shows what it read
}

function row(text: string): HTMLElement {
  return screen.getByText(text).closest("li")!;
}

/** A section's rows, as their Done boxes name them. */
function boxes(section: string): string[] {
  const list = screen.getByRole("region", { name: section });
  return within(list)
    .getAllByRole("checkbox")
    .map((box) => box.getAttribute("aria-label") ?? "");
}

it("lists promises by direction", async () => {
  setApiForTests(promisesApi());
  render(<App />);
  await openPromises();
  expect(screen.getByRole("heading", { level: 1, name: "Open promises" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Promises 3 open" })).toHaveAttribute("aria-current", "page");
  expect(boxes("You promised")).toEqual(["Done: Send the proposal", "Done: Share the deck"]);
  expect(boxes("They promised")).toEqual(["Done: Tell marketing about October 14"]);
  const send = row("Send the proposal");
  expect(send).toHaveTextContent("by Thursday");
  const day = dayLabel(MEETING.started_at, Date.now());
  expect(within(send).getByRole("button", { name: `Priya · Weekly 1:1 · ${day}` })).toBeInTheDocument();
  expect(within(send).getByRole("button", { name: "Jump to 01:50 in the transcript" })).toBeInTheDocument();
  const deck = row("Share the deck"); // no one named yet, and no transcript line to open
  const designDay = dayLabel(DESIGN.started_at, Date.now());
  expect(within(deck).getByRole("button", { name: `Them · Design sync · ${designDay}` })).toBeInTheDocument();
  expect(within(deck).queryByRole("button", { name: /^Jump to/ })).toBeNull();
  // the meeting the rail had open is not marked while the page is open
  expect(screen.getByRole("button", { name: /^Weekly 1:1/ })).not.toHaveAttribute("aria-current");
});

it("says when nothing is open", async () => {
  setApiForTests(makeFakeApi());
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "Promises" }));
  expect(
    await screen.findByText("No open promises. Action items from your 1:1s show up here until you tick them done."),
  ).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "You promised" })).toBeNull();
});

it("ticks a promise done", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const api = promisesApi();
  setApiForTests(api);
  render(<App />);
  await openPromises();
  await userEvent.click(screen.getByRole("checkbox", { name: "Done: Send the proposal" }));
  expect(api.set_item_status).toHaveBeenCalledWith("i1", "done");
  const send = row("Send the proposal");
  expect(within(send).getByRole("checkbox")).toBeChecked();
  expect(send).toHaveTextContent("Done");
  expect(within(send).queryByRole("button", { name: "Not a promise" })).toBeNull();
  expect(screen.getByRole("button", { name: "Promises 2 open" })).toBeInTheDocument(); // at once
  // Python no longer lists it: the row keeps its place, ticked, with Undo, for its 5 seconds
  await changed(api, { you: [DECK], them: [MARKETING] });
  expect(boxes("You promised")).toEqual(["Done: Send the proposal", "Done: Share the deck"]);
  expect(within(row("Send the proposal")).getByRole("button", { name: "Undo" })).toBeInTheDocument();
  await act(() => vi.advanceTimersByTimeAsync(4_000));
  expect(within(row("Send the proposal")).getByRole("button", { name: "Undo" })).toBeInTheDocument();
  await act(() => vi.advanceTimersByTimeAsync(1_100));
  expect(screen.queryByText("Send the proposal")).toBeNull(); // then it leaves
  expect(boxes("You promised")).toEqual(["Done: Share the deck"]);
  expect(screen.getByRole("button", { name: "Promises 2 open" })).toBeInTheDocument();
});

it("undo brings a promise back", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const api = promisesApi();
  setApiForTests(api);
  render(<App />);
  await openPromises();
  await userEvent.click(screen.getByRole("checkbox", { name: "Done: Send the proposal" }));
  await changed(api, { you: [DECK], them: [MARKETING] }); // the refresh no longer lists it
  await userEvent.click(within(row("Send the proposal")).getByRole("button", { name: "Undo" }));
  expect(api.set_item_status).toHaveBeenLastCalledWith("i1", "open");
  const box = screen.getByRole("checkbox", { name: "Done: Send the proposal" });
  expect(box).not.toBeChecked();
  expect(box).toHaveFocus(); // the keyboard stays on the row
  expect(boxes("You promised")).toEqual(["Done: Send the proposal", "Done: Share the deck"]); // in place
  expect(screen.getByRole("button", { name: "Promises 3 open" })).toBeInTheDocument();
  await changed(api, { you: [SEND, DECK], them: [MARKETING] });
  await act(() => vi.advanceTimersByTimeAsync(6_000)); // its 5 seconds no longer run
  expect(boxes("You promised")).toEqual(["Done: Send the proposal", "Done: Share the deck"]);
  expect(within(row("Send the proposal")).getByRole("button", { name: "Not a promise" })).toBeInTheDocument();
});

it("opens the meeting at the line", async () => {
  const shown = vi.spyOn(Element.prototype, "scrollIntoView");
  setApiForTests(promisesApi());
  render(<App />);
  await openPromises();
  // by keyboard: the time tab of the line their promise came from
  within(row("Tell marketing about October 14")).getByRole("button", { name: "Jump to 01:05 in the transcript" }).focus();
  await userEvent.keyboard("{Enter}");
  const transcript = await screen.findByRole("tab", { name: /^Transcript/, selected: true });
  expect(transcript).toHaveFocus(); // the keyboard lands in the meeting
  const line = screen.getByText("Marketing wants October 14.").closest("li");
  expect(line).toHaveAttribute("data-highlighted", "true");
  expect(shown.mock.contexts).toContain(line); // and in view
  expect(screen.getByRole("button", { name: /^Weekly 1:1/ })).toHaveAttribute("aria-current", "true");
  // the meeting link opens the meeting on its note
  await userEvent.click(screen.getByRole("button", { name: "Promises 3 open" }));
  await userEvent.click(within(row("Share the deck")).getByRole("button", { name: /^Them · Design sync/ }));
  expect(await screen.findByRole("heading", { level: 1, name: "Design sync" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Note" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tab", { name: "Note" })).toHaveFocus();
  shown.mockRestore();
});

it("dismisses with not a promise", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const api = promisesApi();
  setApiForTests(api);
  render(<App />);
  await openPromises();
  await userEvent.click(within(row("Send the proposal")).getByRole("button", { name: "Not a promise" }));
  expect(api.set_item_status).toHaveBeenCalledWith("i1", "dismissed");
  const send = row("Send the proposal");
  expect(send).toHaveTextContent("Set aside");
  expect(screen.getByText("Send the proposal")).not.toHaveClass("line-through"); // set aside, not done
  expect(within(send).getByRole("checkbox")).not.toBeChecked();
  expect(within(send).getByRole("button", { name: "Undo" })).toHaveFocus(); // where "Not a promise" was
  expect(screen.getByRole("button", { name: "Promises 2 open" })).toBeInTheDocument(); // at once
  // Python no longer lists it: the row keeps its place, with Undo, for its 5 seconds
  await changed(api, { you: [DECK], them: [MARKETING] });
  expect(boxes("You promised")).toEqual(["Done: Send the proposal", "Done: Share the deck"]);
  await act(() => vi.advanceTimersByTimeAsync(4_000));
  expect(within(row("Send the proposal")).getByRole("button", { name: "Undo" })).toHaveFocus();
  await act(() => vi.advanceTimersByTimeAsync(1_100));
  expect(screen.queryByText("Send the proposal")).toBeNull(); // then it leaves
  expect(screen.getByRole("checkbox", { name: "Done: Share the deck" })).toHaveFocus(); // the next row
  expect(screen.getByRole("button", { name: "Promises 2 open" })).toBeInTheDocument();
});

it("undo puts a set-aside promise back", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const api = promisesApi();
  setApiForTests(api);
  render(<App />);
  await openPromises();
  await userEvent.click(within(row("Send the proposal")).getByRole("button", { name: "Not a promise" }));
  await changed(api, { you: [DECK], them: [MARKETING] }); // the refresh no longer lists it
  await userEvent.keyboard("{Enter}"); // on Undo, which has the focus
  expect(api.set_item_status).toHaveBeenLastCalledWith("i1", "open");
  const box = screen.getByRole("checkbox", { name: "Done: Send the proposal" });
  expect(box).not.toBeChecked();
  expect(box).toHaveFocus(); // the keyboard stays on the row
  expect(boxes("You promised")).toEqual(["Done: Send the proposal", "Done: Share the deck"]); // in place
  expect(screen.getByRole("button", { name: "Promises 3 open" })).toBeInTheDocument();
  await changed(api, { you: [SEND, DECK], them: [MARKETING] });
  await act(() => vi.advanceTimersByTimeAsync(6_000)); // its 5 seconds no longer run
  expect(boxes("You promised")).toEqual(["Done: Send the proposal", "Done: Share the deck"]);
  expect(within(row("Send the proposal")).getByRole("button", { name: "Not a promise" })).toBeInTheDocument();
});
