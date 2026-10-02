import { render, screen, within } from "@testing-library/react";
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

it("says how to start when there are no meetings", () => {
  render(<MeetingList meetings={[]} selectedId={null} liveId={null} onSelect={vi.fn()} />);
  expect(screen.getByText("No meetings yet. Press Record to start one.")).toBeInTheDocument();
});
