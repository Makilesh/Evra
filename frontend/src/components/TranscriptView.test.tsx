import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { Utterance } from "@/bridge";
import { TranscriptView } from "@/components/TranscriptView";
import { DETAIL } from "@/test/fakeApi";

const MORE: Utterance = { id: "u3", channel: 1, speaker: "Them", start_ms: 120_000, end_ms: 121_000, text: "Sounds good." };
const AGAIN: Utterance = { id: "u4", channel: 1, speaker: "Them", start_ms: 123_000, end_ms: 125_000, text: "Talk Friday." };

function scrollBox(height: number) {
  const box = screen.getByTestId("transcript-scroll");
  let top = 0;
  Object.defineProperty(box, "scrollHeight", { configurable: true, get: () => height });
  Object.defineProperty(box, "clientHeight", { configurable: true, get: () => 100 });
  Object.defineProperty(box, "scrollTop", { configurable: true, get: () => top, set: (v: number) => { top = v; } });
  return { box, top: () => top, setTop: (v: number) => { top = v; } };
}

const line = (text: string) => screen.getByText(text).closest("li")!;

it("shows time, speaker and text for each line", () => {
  render(<TranscriptView utterances={DETAIL.utterances} follow={false} highlightId={null} />);
  expect(line("Marketing wants October 14.")).toHaveTextContent("01:05");
  expect(line("Marketing wants October 14.")).toHaveTextContent("Them");
});

it("marks a detent where the speaker changes, and still names the speaker on every line", () => {
  render(<TranscriptView utterances={[...DETAIL.utterances, MORE, AGAIN]} follow={false} highlightId={null} />);
  expect(line("Marketing wants October 14.")).toHaveAttribute("data-turn", "true");
  expect(line("I'll send the proposal by Thursday.")).toHaveAttribute("data-turn", "true");
  expect(line("Sounds good.")).toHaveAttribute("data-turn", "true");
  expect(line("Talk Friday.")).not.toHaveAttribute("data-turn");
  expect(line("Talk Friday.")).toHaveTextContent("Them");
});

it("marks only lines that arrive while live as fresh", () => {
  const { rerender, unmount } = render(<TranscriptView utterances={DETAIL.utterances} follow highlightId={null} />);
  rerender(<TranscriptView utterances={[...DETAIL.utterances, MORE]} follow highlightId={null} />);
  expect(line("Sounds good.")).toHaveAttribute("data-fresh", "true");
  expect(line("Marketing wants October 14.")).not.toHaveAttribute("data-fresh");
  unmount();
  render(<TranscriptView utterances={[...DETAIL.utterances, MORE]} follow={false} highlightId={null} />);
  expect(document.querySelector("[data-fresh]")).toBeNull();
});

it("follows new lines while live, unless the owner scrolled up", () => {
  const { rerender } = render(<TranscriptView utterances={DETAIL.utterances} follow highlightId={null} />);
  const scroll = scrollBox(500);
  rerender(<TranscriptView utterances={[...DETAIL.utterances, MORE]} follow highlightId={null} />);
  expect(scroll.top()).toBe(500);
  scroll.setTop(0);
  fireEvent.scroll(scroll.box);
  rerender(<TranscriptView utterances={[...DETAIL.utterances, MORE, AGAIN]} follow highlightId={null} />);
  expect(scroll.top()).toBe(0);
});

it("highlights and scrolls to a cited line", () => {
  const spy = vi.spyOn(Element.prototype, "scrollIntoView");
  render(<TranscriptView utterances={DETAIL.utterances} follow={false} highlightId="u2" />);
  expect(line("I'll send the proposal by Thursday.")).toHaveAttribute("data-highlighted", "true");
  expect(spy).toHaveBeenCalled();
  spy.mockRestore();
});

it("says when nothing has been transcribed", () => {
  render(<TranscriptView utterances={[]} follow highlightId={null} />);
  expect(screen.getByText("Nothing has been transcribed yet.")).toBeInTheDocument();
});
