import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it } from "vitest";
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

it("records, shows the live transcript, then the note once it is written", async () => {
  let meetings = [MEETING];
  let noted = false;
  const api = makeFakeApi({
    list_meetings: async () => meetings,
    get_meeting: async (id) =>
      id === "m2" ? { meeting: LIVE, utterances: [], note: noted ? DETAIL.note : null } : DETAIL,
  });
  setApiForTests(api);
  render(<App />);
  await screen.findByText("Launch moves to October 14.");

  await userEvent.click(screen.getByRole("button", { name: "Record" }));
  expect(api.start_recording).toHaveBeenCalledWith("");
  meetings = [LIVE, MEETING];
  act(() => emit("recording.state", { state: "recording", meeting_id: "m2", started_at: Date.now() }));
  expect(await screen.findByRole("tab", { name: "Transcript", selected: true })).toBeInTheDocument();
  act(() =>
    emit("transcript.utterance", { meeting_id: "m2", id: "x1", channel: 0, speaker: "You", start_ms: 1_000, end_ms: 2_000, text: "Hello there." }),
  );
  expect(screen.getByText("Hello there.")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Stop" }));
  expect(api.stop_recording).toHaveBeenCalled();
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

it("says so when Python can't be reached", async () => {
  setApiForTests(makeFakeApi({ app_info: async () => { throw new Error("boom"); } }));
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent("couldn't reach its Python side");
});
