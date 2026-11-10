import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { MeetingList } from "@/components/MeetingList";
import { MEETING } from "@/test/fakeApi";

const LIST = [MEETING, { ...MEETING, id: "m3", title: "Design review", has_note: false }];

it("filters by title and says when nothing matches", async () => {
  render(<MeetingList meetings={LIST} selectedId={null} liveId={null} onSelect={vi.fn()} />);
  await userEvent.type(screen.getByRole("searchbox", { name: "Search meetings" }), "design");
  expect(screen.getByRole("button", { name: /Design review/ })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Weekly 1:1/ })).toBeNull();
  await userEvent.type(screen.getByRole("searchbox", { name: "Search meetings" }), "zzz");
  expect(screen.getByText("No meetings match.")).toBeInTheDocument();
});

it("marks the open meeting and the one being recorded, and opens a meeting on click", async () => {
  const onSelect = vi.fn();
  render(<MeetingList meetings={LIST} selectedId="m1" liveId="m3" onSelect={onSelect} />);
  expect(screen.getByRole("button", { name: /Weekly 1:1/ })).toHaveAttribute("aria-current", "true");
  expect(within(screen.getByRole("button", { name: /Design review/ })).getByText(/Recording/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Design review/ }));
  expect(onSelect).toHaveBeenCalledWith("m3");
});

it("says Writing note… for a meeting whose note is being written", () => {
  render(<MeetingList meetings={LIST} selectedId={null} liveId={null} writingIds={["m3"]} onSelect={vi.fn()} />);
  expect(within(screen.getByRole("button", { name: /Design review/ })).getByText("Writing note…")).toBeInTheDocument();
  expect(within(screen.getByRole("button", { name: /Weekly 1:1/ })).getByText("13:51 · 12 min")).toBeInTheDocument();
});

it("groups meetings under Today, Yesterday and their date", () => {
  const now = new Date(2026, 10, 10, 15, 0).getTime();
  const at = (day: number, hour: number) => new Date(2026, 10, day, hour, 0).getTime();
  const meetings = [
    { ...MEETING, id: "a", title: "Weekly 1:1", started_at: at(10, 14) },
    { ...MEETING, id: "b", title: "Design review", started_at: at(10, 10) },
    { ...MEETING, id: "c", title: "Hiring sync", started_at: at(9, 16) },
    { ...MEETING, id: "d", title: "Sprint planning", started_at: at(3, 9) },
  ];
  render(<MeetingList meetings={meetings} selectedId={null} liveId={null} onSelect={vi.fn()} now={() => now} />);
  const headings = screen.getAllByRole("heading").map((h) => h.textContent);
  expect(headings).toEqual(["Today", "Yesterday", "Tue 3 Nov"]);
  expect(within(screen.getByRole("region", { name: "Today" })).getAllByRole("button")).toHaveLength(2);
  expect(within(screen.getByRole("region", { name: "Tue 3 Nov" })).getByRole("button")).toHaveTextContent("Sprint planning");
});

it("Ctrl K focuses the search", () => {
  render(<MeetingList meetings={LIST} selectedId={null} liveId={null} onSelect={vi.fn()} />);
  fireEvent.keyDown(window, { key: "k", ctrlKey: true });
  expect(screen.getByRole("searchbox", { name: "Search meetings" })).toHaveFocus();
});

it("says when there are no meetings yet", () => {
  render(<MeetingList meetings={[]} selectedId={null} liveId={null} onSelect={vi.fn()} />);
  expect(screen.getByText("No meetings yet.")).toBeInTheDocument();
});
