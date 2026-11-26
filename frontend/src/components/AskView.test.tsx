import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { Question, Utterance } from "@/bridge";
import { AskView } from "@/components/AskView";

type Props = Parameters<typeof AskView>[0];

const LINES: Utterance[] = [
  { id: "a", channel: 1, speaker: "Them", start_ms: 0, end_ms: 1_500, text: "Can you send the proposal?" },
  { id: "b", channel: 0, speaker: "You", start_ms: 2_000, end_ms: 4_000, text: "I'll send it by Thursday." },
];

const SUGGESTIONS = ["What did I promise?", "What did they promise?", "What did we decide?", "What's still open?"];

function question(extra: Partial<Question> = {}): Question {
  return { id: "q1", text: "What did I promise?", asked_at: 1, state: "answered", points: [], excerpt: false, ...extra };
}

const ANSWERED = question({
  points: [{ text: "You'll send the proposal by Thursday.", citations: [{ utterance_id: "b", start_ms: 2_000 }] }],
  model: "gemma4:12b",
});

function view(extra: Partial<Props> = {}) {
  const props: Props = {
    questions: [],
    utterances: LINES,
    isLive: false,
    onAsk: vi.fn(async () => null),
    onPrepare: vi.fn(),
    onCite: vi.fn(),
    ...extra,
  };
  return { props, ...render(<AskView {...props} />) };
}

function controls() {
  return {
    input: screen.getByRole("textbox", { name: "Ask about this meeting" }),
    ask: screen.getByRole("button", { name: "Ask" }),
    suggestions: SUGGESTIONS.map((text) => screen.getByRole("button", { name: text })),
  };
}

it("shows an answer's points with their time tabs and quotes", async () => {
  const { props } = view({ questions: [ANSWERED] });
  expect(screen.getByRole("heading", { name: "What did I promise?" })).toBeInTheDocument();
  const row = screen.getByText("You'll send the proposal by Thursday.").closest("li")!;
  const tab = within(row).getByRole("button", { name: "Jump to 00:02 in the transcript" });
  expect(tab).toHaveTextContent("00:02");
  expect(within(row).getByText("I'll send it by Thursday.").tagName).toBe("Q");
  expect(screen.queryByText(/too long to read whole/)).toBeNull();
  await userEvent.click(tab);
  expect(props.onCite).toHaveBeenCalledWith("b");
});

it("asks a suggested question", async () => {
  const { props } = view();
  expect(screen.getByText("Ask anything about this call. Every answer sits beside the lines it came from.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "What did I promise?" }));
  expect(props.onAsk).toHaveBeenCalledWith("What did I promise?");
});

it("asks the typed question on Enter", async () => {
  const { props } = view();
  const { input, ask } = controls();
  expect(input).toHaveAttribute("maxlength", "500");
  expect(input).toHaveAttribute("placeholder", "Ask about this meeting…");
  await userEvent.type(input, "  when is it due  {Enter}");
  expect(props.onAsk).toHaveBeenCalledWith("when is it due");
  expect(input).toHaveValue("");
  await userEvent.type(input, "who owns it");
  await userEvent.click(ask);
  expect(props.onAsk).toHaveBeenLastCalledWith("who owns it");
  await userEvent.click(ask);
  expect(props.onAsk).toHaveBeenCalledTimes(2);
});

it("disables asking while an answer is pending", () => {
  view({ questions: [question({ state: "asking" })] });
  const { input, ask, suggestions } = controls();
  expect(input).toBeDisabled();
  expect(ask).toBeDisabled();
  suggestions.forEach((button) => expect(button).toBeDisabled());
  expect(screen.getByText("Reading the meeting…")).toBeInTheDocument();
});

it("says when the meeting doesn't answer", () => {
  view({ questions: [question({ state: "not_found" })] });
  expect(screen.getByText("Not discussed in this meeting.")).toBeInTheDocument();
});

it("says when an answer couldn't be checked", () => {
  view({ questions: [question({ state: "unchecked" })] });
  expect(
    screen.getByText("Evra found an answer but couldn't check it against the transcript, so it isn't shown."),
  ).toBeInTheDocument();
});

it("failed question offers ask again", async () => {
  const { props } = view({ questions: [question({ state: "failed", reason: "ollama_down", text: "When is it due?" })] });
  expect(
    screen.getByText("Ollama isn't running. Start it from the system tray (or install it from ollama.com)."),
  ).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Ask again" }));
  expect(props.onAsk).toHaveBeenCalledWith("When is it due?");
});

it("excerpt answer says it read parts", () => {
  view({ questions: [{ ...ANSWERED, excerpt: true }] });
  expect(
    screen.getByText("This call is too long to read whole, so Evra read the parts that match your question."),
  ).toBeInTheDocument();
});

it("says a long call had no part matching the question, and when it read parts", () => {
  view({ questions: [question({ state: "not_found", excerpt: true })] });
  expect(screen.getByText("Not discussed in this meeting.")).toBeInTheDocument();
  expect(
    screen.getByText(
      "This call is too long to read whole, and no part of it matches the words of your question.",
    ),
  ).toBeInTheDocument();
});

it("an unchecked answer from a long call says it read parts", () => {
  view({ questions: [question({ state: "unchecked", excerpt: true })] });
  expect(
    screen.getByText("This call is too long to read whole, so Evra read the parts that match your question."),
  ).toBeInTheDocument();
});

it("a failed question loses Ask again once a later question has the same text", () => {
  const failed = question({ id: "q1", state: "failed", reason: "timeout", text: "When is it due?" });
  const { rerender, props } = view({ questions: [failed] });
  expect(screen.getByRole("button", { name: "Ask again" })).toBeInTheDocument();
  rerender(<AskView {...props} questions={[failed, question({ id: "q2", text: "When is it due?" })]} />);
  expect(screen.queryByRole("button", { name: "Ask again" })).toBeNull();
  rerender(<AskView {...props} questions={[failed, question({ id: "q2", text: "Who owns it?" })]} />);
  expect(screen.getByRole("button", { name: "Ask again" })).toBeInTheDocument();
});

it("waits for the recording to end", () => {
  const { props } = view({ isLive: true });
  expect(screen.getByText("You can ask once the recording ends.")).toBeInTheDocument();
  expect(screen.queryByText(/Ask anything about this call/)).toBeNull();
  const { input, ask, suggestions } = controls();
  expect(input).toBeDisabled();
  expect(ask).toBeDisabled();
  suggestions.forEach((button) => expect(button).toBeDisabled());
  expect(props.onPrepare).not.toHaveBeenCalled();
});

it("prepares the meeting once on open", () => {
  const { props, rerender, unmount } = view();
  rerender(<AskView {...props} questions={[ANSWERED]} />);
  expect(props.onPrepare).toHaveBeenCalledTimes(1);
  unmount();
  const silent = view({ utterances: [] });
  expect(silent.props.onPrepare).not.toHaveBeenCalled();
});

it("shows a refusal", async () => {
  view({ onAsk: vi.fn(async () => "busy" as const) });
  await userEvent.click(screen.getByRole("button", { name: "What did I promise?" }));
  expect(await screen.findByText("Evra is still answering the last question.")).toBeInTheDocument();
});

it("keeps a refused question in the box", async () => {
  view({ onAsk: vi.fn(async () => "recording" as const) });
  const { input } = controls();
  await userEvent.type(input, "when is it due{Enter}");
  expect(await screen.findByText("You can ask once the recording ends.")).toBeInTheDocument();
  expect(input).toHaveValue("when is it due");
});

it("announces when an answer is ready", () => {
  const { props, rerender } = view({ questions: [question({ state: "asking" })] });
  const status = screen.getByRole("status");
  expect(status).toHaveTextContent("");
  rerender(<AskView {...props} questions={[ANSWERED]} />);
  expect(status).toHaveTextContent("Answer ready");
});

it("announces a failed question with its reason", () => {
  const { props, rerender } = view({ questions: [question({ state: "asking" })] });
  rerender(<AskView {...props} questions={[question({ state: "failed", reason: "ollama_down" })]} />);
  expect(screen.getByRole("status")).toHaveTextContent(
    "Ollama isn't running. Start it from the system tray (or install it from ollama.com).",
  );
});

it("announces that an accepted question is being read", async () => {
  view();
  await userEvent.click(screen.getByRole("button", { name: "What did I promise?" }));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Reading the meeting…"));
});

it("keeps the answer's announcement when the answer lands before the reply", async () => {
  let land = () => {};
  const { props, rerender } = view({
    onAsk: vi.fn(async () => {
      land();
      return null;
    }),
  });
  land = () => rerender(<AskView {...props} questions={[ANSWERED]} />);
  await userEvent.click(screen.getByRole("button", { name: "What did I promise?" }));
  await waitFor(() => expect(props.onAsk).toHaveBeenCalled());
  expect(screen.getByRole("status")).toHaveTextContent("Answer ready");
});

it("offers Ask again only where asking again can help", () => {
  view({
    questions: [
      question({ state: "failed", reason: "too_long" }),
      question({ id: "q2", text: "When is it due?", state: "failed", reason: "no_transcript" }),
    ],
  });
  expect(screen.getByText("This question needs more room than the model's settings allow.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Ask again" })).toBeNull();
});

it("prepares once though its callback is a new function on every render", () => {
  const prepare = vi.fn();
  const { props, rerender } = view({ onPrepare: () => prepare() });
  rerender(<AskView {...props} onPrepare={() => prepare()} />);
  rerender(<AskView {...props} onPrepare={() => prepare()} questions={[ANSWERED]} />);
  expect(prepare).toHaveBeenCalledTimes(1);
});

it("scrolls the newest question into view when it is added, and again when its answer lands", () => {
  const scroll = vi.spyOn(Element.prototype, "scrollIntoView");
  const { props, rerender } = view({ questions: [ANSWERED] });
  expect(scroll).not.toHaveBeenCalled();
  const next = question({ id: "q2", text: "When is it due?", state: "asking" });
  rerender(<AskView {...props} questions={[ANSWERED, next]} />);
  const section = screen.getByRole("heading", { name: "When is it due?" }).closest("section");
  expect(scroll).toHaveBeenCalledTimes(1);
  expect(scroll.mock.contexts[0]).toBe(section);
  rerender(<AskView {...props} questions={[ANSWERED, { ...next, state: "not_found" }]} />);
  expect(scroll).toHaveBeenCalledTimes(2);
  expect(scroll.mock.contexts[1]).toBe(section);
  scroll.mockRestore();
});
