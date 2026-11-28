import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import App from "@/App";
import { emit, setApiForTests, type MeetingSummary } from "@/bridge";
import { DETAIL, MEETING, makeFakeApi } from "@/test/fakeApi";

afterEach(() => setApiForTests(null));

const LIVE: MeetingSummary = {
  ...MEETING,
  id: "m2",
  title: "Recording 2026-09-28 13:51",
  state: "recording",
  has_note: false,
  duration_ms: null,
};

it("opens on the newest meeting's note and jumps from a citation to its transcript line", async () => {
  setApiForTests(makeFakeApi());
  render(<App />);
  expect(await screen.findByText("Launch moves to October 14.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Jump to 01:05 in the transcript" }));
  expect(screen.getByRole("tab", { name: "Transcript" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("Marketing wants October 14.").closest("li")).toHaveAttribute("data-highlighted", "true");
});

it("records, takes notes beside the live transcript, then shows the note once it is written", async () => {
  let meetings = [MEETING];
  let noted = false;
  const api = makeFakeApi({
    list_meetings: async () => meetings,
    get_meeting: async (id) =>
      id === "m2"
        ? { meeting: LIVE, utterances: [], note: noted ? DETAIL.note : null, questions: [], notes: [], with: null }
        : DETAIL,
  });
  setApiForTests(api);
  render(<App />);
  await screen.findByText("Launch moves to October 14.");

  await userEvent.click(screen.getByRole("button", { name: "Record" }));
  expect(api.start_recording).toHaveBeenCalledWith("");
  meetings = [LIVE, MEETING];
  act(() => emit("recording.state", { state: "recording", meeting_id: "m2", started_at: Date.now() }));
  expect(await screen.findByRole("tab", { name: "My notes", selected: true })).toBeInTheDocument();
  act(() =>
    emit("transcript.utterance", { meeting_id: "m2", id: "x1", channel: 0, speaker: "You", start_ms: 1_000, end_ms: 2_000, text: "Hello there." }),
  );
  expect(screen.getByText("Hello there.")).toBeInTheDocument(); // under the pad
  await userEvent.type(screen.getByRole("textbox", { name: "Note line 1" }), "Said hello");

  await userEvent.click(screen.getByRole("button", { name: "Stop" }));
  await waitFor(() => expect(api.stop_recording).toHaveBeenCalled());
  expect(api.save_notes).toHaveBeenCalledTimes(1); // at once, not 400 ms later
  expect(api.save_notes).toHaveBeenCalledWith("m2", [expect.objectContaining({ text: "Said hello", pasted: false })]);
  const [saved] = vi.mocked(api.save_notes).mock.invocationCallOrder;
  const [stopped] = vi.mocked(api.stop_recording).mock.invocationCallOrder;
  expect(saved).toBeLessThan(stopped);
  act(() => {
    emit("recording.state", { state: "processing", meeting_id: "m2" });
    emit("note.stage", { meeting_id: "m2", stage: "writing" });
  });
  expect(await screen.findByRole("status")).toHaveTextContent("Writing note…");
  expect(screen.getByRole("button", { name: "Writing note…" })).toBeDisabled();

  noted = true;
  act(() => {
    emit("note.ready", { meeting_id: "m2" });
    emit("recording.state", { state: "idle" });
  });
  expect(await screen.findByText("Launch moves to October 14.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Record" })).toBeEnabled();
});

it("explains a failed note and retries it", async () => {
  const api = makeFakeApi({ get_meeting: async () => ({ ...DETAIL, note: null }) });
  setApiForTests(api);
  render(<App />);
  await screen.findByRole("button", { name: "Write note" });
  act(() => emit("note.failed", { meeting_id: "m1", reason: "ollama_down" }));
  expect(screen.getByRole("alert")).toHaveTextContent("Ollama isn't running");
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(api.write_note).toHaveBeenCalledWith("m1");
});

it("shows why recording could not start", async () => {
  setApiForTests(
    makeFakeApi({
      start_recording: async () => ({
        ok: false,
        error: "microphone 'Headset' is not connected",
        hint: "Pick the microphone again in Evra, or check that it is connected and turned on.",
      }),
    }),
  );
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "Record" }));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("is not connected");
  expect(alert).toHaveTextContent("Pick the microphone again");
});

it("renames a meeting", async () => {
  const api = makeFakeApi();
  setApiForTests(api);
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "Rename meeting" }));
  const input = screen.getByRole("textbox", { name: "Meeting title" });
  await userEvent.clear(input);
  await userEvent.type(input, "Sync with Priya{Enter}");
  expect(api.rename_meeting).toHaveBeenCalledWith("m1", "Sync with Priya");
});

it("shows the name Evra gives a meeting, but never over a rename being typed", async () => {
  setApiForTests(makeFakeApi());
  render(<App />);
  await screen.findByText("Launch moves to October 14.");
  act(() => emit("meeting.renamed", { meeting_id: "m1", title: "Launch date and designer proposal" }));
  expect(screen.getByRole("heading", { level: 1, name: "Launch date and designer proposal" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^Launch date and designer proposal/ })).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Rename meeting" }));
  const input = screen.getByRole("textbox", { name: "Meeting title" });
  await userEvent.clear(input);
  await userEvent.type(input, "Sync with Priya");
  act(() => emit("meeting.renamed", { meeting_id: "m1", title: "Something else" }));
  expect(input).toHaveValue("Sync with Priya");
});

it("shows transcript and note text as text, never as HTML", async () => {
  const evil = "<img src=x onerror=alert(1)> </script><b>bold</b>";
  setApiForTests(
    makeFakeApi({
      get_meeting: async () => ({
        ...DETAIL,
        note: { model: "m", sections: [{ id: "summary", title: "Summary", blocks: [{ text: evil, citations: [] }] }] },
      }),
    }),
  );
  render(<App />);
  expect(await screen.findByText(evil)).toBeInTheDocument();
  expect(document.querySelector("img")).toBeNull();
  expect(document.querySelector("b")).toBeNull();
});

it("opens Settings from the rail and with Ctrl+comma; Esc goes back to the meeting", async () => {
  setApiForTests(makeFakeApi());
  render(<App />);
  await screen.findByText("Launch moves to October 14.");
  await userEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(screen.getByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
  expect(screen.queryByText("Launch moves to October 14.")).toBeNull();
  expect(screen.getByRole("button", { name: /Weekly 1:1/ })).not.toHaveAttribute("aria-current");
  await userEvent.keyboard("{Escape}");
  expect(await screen.findByText("Launch moves to October 14.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Settings" })).toHaveFocus();
  await userEvent.keyboard("{Control>},{/Control}");
  expect(screen.getByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Weekly 1:1/ }));
  expect(await screen.findByText("Launch moves to October 14.")).toBeInTheDocument();
});

it("closes Settings back to the page it was opened from", async () => {
  setApiForTests(makeFakeApi());
  render(<App />);
  await screen.findByText("Launch moves to October 14.");
  await userEvent.click(screen.getByRole("button", { name: "Promises" }));
  expect(await screen.findByRole("heading", { level: 1, name: "Open promises" })).toBeInTheDocument();
  await userEvent.keyboard("{Control>},{/Control}");
  expect(screen.getByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  expect(screen.getByRole("heading", { level: 1, name: "Open promises" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Promises" })).toHaveAttribute("aria-current", "page");
});

it("turns dark at once and saves it", async () => {
  const api = makeFakeApi();
  setApiForTests(api);
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "Settings" }));
  await userEvent.click(screen.getByRole("radio", { name: "Dark" }));
  expect(document.documentElement).toHaveClass("dark");
  expect(api.set_theme).toHaveBeenCalledWith("dark");
  expect(screen.getByRole("radio", { name: "Dark" })).toBeChecked();
  document.documentElement.classList.remove("dark");
});

it("says when a setting could not be saved", async () => {
  setApiForTests(makeFakeApi({ set_note_model: async () => ({ ok: false }) }));
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "Settings" }));
  const select = screen.getByRole("combobox", { name: "Note model" });
  await waitFor(() => expect(select).toBeEnabled());
  await userEvent.selectOptions(select, "qwen3.5:9b");
  expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't save that change.");
});

it("says so when Python can't be reached", async () => {
  setApiForTests(makeFakeApi({ app_info: async () => { throw new Error("boom"); } }));
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent("couldn't reach its Python side");
});

it("welcomes a first run with what Record does and the two shortcuts", async () => {
  setApiForTests(makeFakeApi({ list_meetings: async () => [] }));
  render(<App />);
  const title = await screen.findByRole("heading", { name: "Press Record when the call starts." });
  // the window never scrolls as a whole (index.css): the welcome scrolls in its own scroller
  expect(title.closest(".overflow-y-auto")).not.toBeNull();
  const shortcuts = screen.getByRole("list", { name: "Shortcuts" });
  expect(shortcuts).toHaveTextContent("Ctrl K");
  expect(shortcuts).toHaveTextContent("Search your meetings");
  expect(shortcuts).toHaveTextContent("Ctrl ,");
  expect(shortcuts).toHaveTextContent("Settings");
});

it("asks about the open meeting and shows the answer when it arrives", async () => {
  const api = makeFakeApi();
  setApiForTests(api);
  render(<App />);
  await screen.findByText("Launch moves to October 14.");
  await userEvent.click(screen.getByRole("tab", { name: "Ask" }));
  expect(api.prepare_ask).toHaveBeenCalledWith("m1");
  await userEvent.type(screen.getByRole("textbox", { name: "Ask about this meeting" }), "What did I promise?{Enter}");
  expect(api.ask_meeting).toHaveBeenCalledWith("m1", "What did I promise?");
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Reading the meeting…"));
  expect(screen.getByRole("textbox", { name: "Ask about this meeting" })).toBeDisabled();
  act(() =>
    emit("question.updated", {
      meeting_id: "m1",
      question: {
        id: "q1",
        text: "What did I promise?",
        asked_at: 1,
        state: "answered",
        points: [{ text: "You'll send the proposal by Thursday.", citations: [{ utterance_id: "u2", start_ms: 110_000 }] }],
        excerpt: false,
        model: "gemma4:12b",
      },
    }),
  );
  expect(screen.getByText("You'll send the proposal by Thursday.")).toBeInTheDocument();
  expect(screen.queryByText("Reading the meeting…")).toBeNull();
  expect(screen.getByRole("status")).toHaveTextContent("Answer ready");
  expect(screen.getByRole("textbox", { name: "Ask about this meeting" })).toBeEnabled();
});

it("drops the Ask tab's refusal once the note job it waits for ends", async () => {
  const ask_meeting = vi
    .fn()
    .mockResolvedValueOnce({ ok: false, reason: "note" })
    .mockResolvedValueOnce({ ok: false, reason: "recording" });
  setApiForTests(makeFakeApi({ ask_meeting }));
  render(<App />);
  await screen.findByText("Launch moves to October 14.");
  await userEvent.click(screen.getByRole("tab", { name: "Ask" }));
  // another meeting's note is being written: a question waits for it
  act(() => emit("note.stage", { meeting_id: "m2", stage: "writing" }));
  await userEvent.click(screen.getByRole("button", { name: "What did I promise?" }));
  expect(await screen.findByText("You can ask once the note is written.")).toBeInTheDocument();
  act(() => emit("note.ready", { meeting_id: "m2" }));
  expect(screen.queryByText("You can ask once the note is written.")).toBeNull();
  // refused for a recording: its note job ends without a note, and the wait with it
  await userEvent.click(screen.getByRole("button", { name: "What did I promise?" }));
  expect(await screen.findByText("You can ask once the recording ends.")).toBeInTheDocument();
  act(() => emit("note.stage", { meeting_id: "m2", stage: "writing" }));
  expect(screen.getByText("You can ask once the recording ends.")).toBeInTheDocument();
  act(() => emit("note.failed", { meeting_id: "m2", reason: "ollama_down" }));
  expect(screen.queryByText("You can ask once the recording ends.")).toBeNull();
  expect(screen.getByRole("tab", { name: "Ask", selected: true })).toBeInTheDocument(); // the tab stayed open
});
