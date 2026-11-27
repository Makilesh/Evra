import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import App from "@/App";
import { emit, setApiForTests, type EvraApi } from "@/bridge";
import { dayLabel } from "@/format";
import { BRIEF, BUDGET, WEEKLY, peopleApi } from "@/test/fakePeople";

afterEach(() => {
  vi.useRealTimers();
  setApiForTests(null);
});

/** Priya's page, opened from the People page, once Python has read it. */
async function openPriya(api: EvraApi = peopleApi()): Promise<EvraApi> {
  setApiForTests(api);
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "People" }));
  await userEvent.click(await screen.findByRole("button", { name: /^Priya/ }));
  await screen.findByRole("region", { name: "From your last 1:1" });
  return api;
}

const region = (name: string, inside: HTMLElement = document.body) => within(inside).getByRole("region", { name });
const boxes = (inside: HTMLElement) =>
  within(inside)
    .getAllByRole("checkbox")
    .map((box) => box.getAttribute("aria-label"));

it("shows open promises and last time", async () => {
  const shown = vi.spyOn(Element.prototype, "scrollIntoView");
  await openPriya();
  // their open promises both ways, as the Promises page shows them; no one else's
  const promises = region("Open promises");
  expect(boxes(region("You promised", promises))).toEqual(["Done: Send the proposal"]);
  expect(boxes(region("They promised", promises))).toEqual(["Done: Tell marketing about October 14"]);
  expect(screen.queryByText("Write up the interview loop")).toBeNull(); // Sam's
  expect(screen.queryByText("Share the deck")).toBeNull(); // from a 1:1 with no one named
  // from their last 1:1: what was left for next time and what is still open, each with its meeting
  const last = region("From your last 1:1");
  const day = dayLabel(WEEKLY.started_at, Date.now());
  const next = region("For next time", last);
  expect(next).toHaveTextContent("Mentoring a new hire: talk to Sam.");
  expect(region("Open questions", last)).toHaveTextContent("Can the API limit go to 500 requests a minute?");
  expect(within(last).getAllByRole("button", { name: `Weekly 1:1 · ${day}` })).toHaveLength(2);
  // their 1:1s, newest first
  const meetings = within(region("Meetings")).getAllByRole("button");
  expect(meetings.map((m) => m.textContent)).toEqual([
    expect.stringContaining("Weekly 1:1"),
    expect.stringContaining("Budget check"),
  ]);
  // a time tab opens that meeting's transcript at the line, by keyboard
  within(next).getByRole("button", { name: "Jump to 01:50 in the transcript" }).focus();
  await userEvent.keyboard("{Enter}");
  expect(await screen.findByRole("tab", { name: /^Transcript/, selected: true })).toHaveFocus();
  const line = screen.getByText("I'll send the proposal by Thursday.").closest("li");
  expect(line).toHaveAttribute("data-highlighted", "true");
  expect(shown.mock.contexts).toContain(line);
  shown.mockRestore();
});

it("opens a meeting from the list on its note", async () => {
  await openPriya();
  await userEvent.click(within(region("Meetings")).getByRole("button", { name: /^Budget check/ }));
  expect(await screen.findByRole("heading", { level: 1, name: "Budget check" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Note" })).toHaveFocus();
});

it("writes a brief", async () => {
  const api = await openPriya();
  const catchUp = region("Catch me up");
  await userEvent.click(within(catchUp).getByRole("button", { name: "Write a brief" }));
  expect(api.write_brief).toHaveBeenCalledWith("p1");
  expect(within(catchUp).getByRole("status")).toHaveTextContent("Writing the brief…");
  expect(within(catchUp).getByRole("button", { name: "Write a brief" })).toBeDisabled();
  act(() => emit("brief.updated", { person_id: "p1", state: "written", brief: BRIEF }));
  expect(within(catchUp).queryByRole("status")).toBeNull();
  // when it was written, above its points (RC10): a brief is a snapshot
  const written = within(catchUp).getByText(`Written ${dayLabel(BRIEF.created_at, Date.now())}`);
  const first = screen.getByText("You still owe Priya the proposal, due Thursday.");
  expect(written.compareDocumentPosition(first) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  // each point with the meetings it comes from
  const day = dayLabel(WEEKLY.started_at, Date.now());
  const budgetDay = dayLabel(BUDGET.started_at, Date.now());
  const links = (text: string) =>
    within(screen.getByText(text).closest("li")!)
      .getAllByRole("button")
      .map((b) => b.textContent);
  expect(links("You still owe Priya the proposal, due Thursday.")).toEqual([`Weekly 1:1 · ${day}`]);
  expect(links("The contractor budget is twelve thousand dollars.")).toEqual([
    `Budget check · ${budgetDay}`,
    `Weekly 1:1 · ${day}`,
  ]);
  expect(within(catchUp).getByRole("button", { name: "Write again" })).toBeEnabled();
  // a meeting it cites opens on its note
  await userEvent.click(within(catchUp).getByRole("button", { name: `Budget check · ${budgetDay}` }));
  expect(await screen.findByRole("heading", { level: 1, name: "Budget check" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Note" })).toHaveFocus();
});

it("says why there is no brief to show", async () => {
  const write_brief = vi
    .fn()
    .mockResolvedValueOnce({ ok: false, reason: "busy" })
    .mockResolvedValueOnce({ ok: false, reason: "recording" })
    .mockResolvedValue({ ok: true });
  await openPriya(peopleApi({ write_brief }));
  const catchUp = region("Catch me up");
  await userEvent.click(within(catchUp).getByRole("button", { name: "Write a brief" }));
  expect(catchUp).toHaveTextContent("Evra is busy answering a question or writing a brief. Try again when it's done.");
  expect(within(catchUp).queryByRole("status")).toBeNull();
  // a recording first (RC9): said the same way, with the focus kept, and brought into view
  const shown = vi.spyOn(Element.prototype, "scrollIntoView");
  const write = within(catchUp).getByRole("button", { name: "Write a brief" });
  write.focus();
  await userEvent.keyboard("{Enter}");
  expect(catchUp).toHaveTextContent("You can write a brief once the recording ends.");
  expect(catchUp).not.toHaveTextContent("Evra is busy");
  expect(write).toHaveFocus();
  expect(shown.mock.contexts.some((el) => catchUp.contains(el as Node))).toBe(true);
  shown.mockRestore();
  await userEvent.click(within(catchUp).getByRole("button", { name: "Write a brief" }));
  act(() => emit("brief.updated", { person_id: "p1", state: "unchecked" }));
  expect(catchUp).toHaveTextContent("Evra couldn't check a brief against your notes, so none is shown.");
  expect(catchUp).not.toHaveTextContent("once the recording ends");
  await userEvent.click(within(catchUp).getByRole("button", { name: "Write again" }));
  act(() => emit("brief.updated", { person_id: "p1", state: "failed", reason: "ollama_down" }));
  expect(within(catchUp).getByRole("alert")).toHaveTextContent("Ollama isn't running");
  // a new brief that can't be checked, over an earlier one: the earlier one stays, and it says so (RC10)
  await userEvent.click(within(catchUp).getByRole("button", { name: "Write again" }));
  act(() => emit("brief.updated", { person_id: "p1", state: "written", brief: BRIEF }));
  await userEvent.click(within(catchUp).getByRole("button", { name: "Write again" }));
  act(() => emit("brief.updated", { person_id: "p1", state: "unchecked" }));
  expect(catchUp).toHaveTextContent(
    "Evra couldn't check the new brief against your notes, so the earlier one is still shown.",
  );
  expect(catchUp).not.toHaveTextContent("so none is shown");
  expect(within(catchUp).getByText("You still owe Priya the proposal, due Thursday.")).toBeInTheDocument();
  expect(within(catchUp).getByText(`Written ${dayLabel(BRIEF.created_at, Date.now())}`)).toBeInTheDocument();
  // someone with no note from a 1:1 yet is told so, with nothing to press
  await userEvent.click(screen.getByRole("button", { name: "People" }));
  await userEvent.click(await screen.findByRole("button", { name: /^Sam Lee/ }));
  await screen.findByRole("region", { name: "Meetings" });
  const theirs = region("Catch me up");
  expect(theirs).toHaveTextContent("There's no note from a 1:1 with them yet.");
  expect(within(theirs).queryByRole("button")).toBeNull();
  expect(write_brief).toHaveBeenCalledTimes(6);
});

it("renames a person", async () => {
  const api = await openPriya();
  const reads = vi.mocked(api.list_promises).mock.calls.length;
  // Escape keeps the name
  await userEvent.click(screen.getByRole("button", { name: "Rename person" }));
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("textbox", { name: "Name" })).toBeNull();
  expect(screen.getByRole("button", { name: "Rename person" })).toHaveFocus();
  // a name someone else has, and "You", are refused with the input kept open
  await userEvent.keyboard("{Enter}");
  const input = screen.getByRole("textbox", { name: "Name" });
  expect(input).toHaveValue("Priya");
  expect(input).toHaveFocus();
  await userEvent.clear(input);
  await userEvent.type(input, "sam lee{Enter}");
  expect(api.rename_person).toHaveBeenLastCalledWith("p1", "sam lee");
  expect(await screen.findByText("Someone else already has that name.")).toBeInTheDocument();
  expect(input).toHaveFocus();
  expect(input).toHaveAttribute("aria-invalid", "true");
  await userEvent.clear(input);
  await userEvent.type(input, "You{Enter}");
  expect(await screen.findByText("Evra shows you as “You”. Pick another name.")).toBeInTheDocument();
  expect(screen.queryByText("Someone else already has that name.")).toBeNull();
  expect(input).toHaveFocus();
  // a free name is theirs everywhere they show
  await userEvent.clear(input);
  await userEvent.type(input, "Priya Shah{Enter}");
  expect(await screen.findByRole("heading", { level: 1, name: "Priya Shah" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Rename person" })).toHaveFocus();
  await waitFor(() => expect(vi.mocked(api.list_promises).mock.calls.length).toBeGreaterThan(reads));
  // both of her promise rows name her again
  expect(await screen.findAllByRole("button", { name: /^Priya Shah · Weekly 1:1/ })).toHaveLength(2);
  await userEvent.click(screen.getByRole("button", { name: "People" }));
  expect(await screen.findByRole("button", { name: /^Priya Shah/ })).toBeInTheDocument();
});

it("forgets a person", async () => {
  const api = await openPriya();
  await userEvent.click(screen.getByRole("button", { name: "Forget this person" }));
  const sure = "Forget Priya? Their meetings say “Them” again, and their brief is deleted.";
  const keep = within(screen.getByRole("group", { name: sure })).getByRole("button", { name: "Keep" });
  expect(keep).toHaveFocus(); // the safe choice first
  await userEvent.click(keep);
  expect(screen.queryByRole("group", { name: sure })).toBeNull();
  expect(screen.getByRole("button", { name: "Forget this person" })).toHaveFocus();
  // Escape keeps them too
  await userEvent.keyboard("{Enter}");
  expect(screen.getByRole("group", { name: sure })).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  expect(screen.getByRole("button", { name: "Forget this person" })).toHaveFocus();
  expect(api.remove_person).not.toHaveBeenCalled();
  // Forget: back on People, without them
  const reads = vi.mocked(api.list_promises).mock.calls.length;
  await userEvent.click(screen.getByRole("button", { name: "Forget this person" }));
  await userEvent.click(screen.getByRole("button", { name: "Forget" }));
  expect(api.remove_person).toHaveBeenCalledWith("p1");
  expect(await screen.findByRole("heading", { level: 1, name: "People" })).toHaveFocus();
  await waitFor(() => expect(screen.queryByRole("button", { name: /^Priya/ })).toBeNull());
  expect(screen.getByRole("button", { name: /^Sam Lee/ })).toBeInTheDocument();
  expect(vi.mocked(api.list_promises).mock.calls.length).toBeGreaterThan(reads);
});

it("ticks a promise on a person's page as on the Promises page", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const api = await openPriya();
  expect(screen.getByRole("button", { name: "Promises 4 open" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("checkbox", { name: "Done: Send the proposal" }));
  expect(api.set_item_status).toHaveBeenCalledWith("i1", "done");
  const send = screen.getByText("Send the proposal").closest("li")!;
  expect(within(send).getByRole("checkbox")).toBeChecked();
  expect(send).toHaveTextContent("Done");
  expect(screen.getByRole("button", { name: "Promises 3 open" })).toBeInTheDocument(); // at once
  act(() => emit("promises.changed", {})); // Python no longer lists it
  await act(() => vi.advanceTimersByTimeAsync(4_000));
  expect(within(send).getByRole("button", { name: "Undo" })).toBeInTheDocument();
  await act(() => vi.advanceTimersByTimeAsync(1_100));
  expect(screen.queryByText("Send the proposal")).toBeNull(); // then it leaves
  expect(screen.getByRole("heading", { level: 1, name: "Priya" })).toHaveFocus(); // none in its place
  await userEvent.click(screen.getByRole("button", { name: "Promises 3 open" }));
  await screen.findByRole("heading", { level: 1, name: "Open promises" });
  expect(screen.getByRole("checkbox", { name: "Done: Tell marketing about October 14" })).toBeInTheDocument();
  expect(screen.queryByText("Send the proposal")).toBeNull(); // gone from the Promises page too
});

it("closes Settings back to a person's page", async () => {
  await openPriya();
  await userEvent.keyboard("{Control>},{/Control}");
  expect(screen.getByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  expect(await screen.findByRole("heading", { level: 1, name: "Priya" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "People" })).toHaveAttribute("aria-current", "page");
});
