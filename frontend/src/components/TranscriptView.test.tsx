import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { Utterance } from "@/bridge";
import { TranscriptView } from "@/components/TranscriptView";
import { DETAIL } from "@/test/fakeApi";

const MORE: Utterance = { id: "u3", channel: 1, speaker: "Them", start_ms: 120_000, end_ms: 121_000, text: "Sounds good." };

function scrollBox(height: number) {
  const box = screen.getByTestId("transcript-scroll");
  let top = 0;
  Object.defineProperty(box, "scrollHeight", { configurable: true, get: () => height });
  Object.defineProperty(box, "clientHeight", { configurable: true, get: () => 100 });
  Object.defineProperty(box, "scrollTop", { configurable: true, get: () => top, set: (v: number) => { top = v; } });
  return { box, top: () => top, setTop: (v: number) => { top = v; } };
}

it("shows time, speaker and text for each line", () => {
  render(<TranscriptView utterances={DETAIL.utterances} follow={false} highlightId={null} />);
  const line = screen.getByText("Marketing wants October 14.").closest("li")!;
  expect(line).toHaveTextContent("01:05");
  expect(line).toHaveTextContent("Them");
});

it("follows new lines while live, unless the owner scrolled up", () => {
  const { rerender } = render(<TranscriptView utterances={DETAIL.utterances} follow highlightId={null} />);
  const scroll = scrollBox(500);
  rerender(<TranscriptView utterances={[...DETAIL.utterances, MORE]} follow highlightId={null} />);
  expect(scroll.top()).toBe(500);
  scroll.setTop(0);
  fireEvent.scroll(scroll.box);
  rerender(
    <TranscriptView utterances={[...DETAIL.utterances, MORE, { ...MORE, id: "u4" }]} follow highlightId={null} />,
  );
  expect(scroll.top()).toBe(0);
});

it("highlights and scrolls to a cited line", () => {
  const spy = vi.spyOn(Element.prototype, "scrollIntoView");
  render(<TranscriptView utterances={DETAIL.utterances} follow={false} highlightId="u2" />);
  const line = screen.getByText("I'll send the proposal by Thursday.").closest("li")!;
  expect(line).toHaveAttribute("data-highlighted", "true");
  expect(spy).toHaveBeenCalled();
  spy.mockRestore();
});

it("says when nothing has been transcribed", () => {
  render(<TranscriptView utterances={[]} follow highlightId={null} />);
  expect(screen.getByText("Nothing has been transcribed yet.")).toBeInTheDocument();
});
