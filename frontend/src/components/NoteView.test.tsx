import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { NoteView } from "@/components/NoteView";
import { DETAIL } from "@/test/fakeApi";

it("shows sections with citation chips that jump to the transcript", async () => {
  const onCite = vi.fn();
  render(<NoteView note={DETAIL.note} status={undefined} canWrite onWrite={vi.fn()} onCite={onCite} />);
  expect(screen.getByRole("heading", { name: "Action items" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Jump to 01:50 in the transcript" }));
  expect(onCite).toHaveBeenCalledWith("u2");
});

it("shows progress instead of an old note while a new one is written", () => {
  render(<NoteView note={DETAIL.note} status={{ stage: "writing" }} canWrite={false} onWrite={vi.fn()} onCite={vi.fn()} />);
  expect(screen.getByRole("status")).toHaveTextContent("Writing note…");
  expect(screen.queryByText("Launch moves to October 14.")).toBeNull();
});

it("explains a failure and offers Retry only when it can help", async () => {
  const onWrite = vi.fn();
  const { rerender } = render(
    <NoteView note={null} status={{ failed: { reason: "invalid" } }} canWrite onWrite={onWrite} onCite={vi.fn()} />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("The model didn't return a valid note.");
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(onWrite).toHaveBeenCalled();
  rerender(<NoteView note={null} status={{ failed: { reason: "too_long" } }} canWrite onWrite={onWrite} onCite={vi.fn()} />);
  expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
});

it("offers to write a note for a meeting that has none", async () => {
  const onWrite = vi.fn();
  render(<NoteView note={null} status={undefined} canWrite onWrite={onWrite} onCite={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: "Write note" }));
  expect(onWrite).toHaveBeenCalled();
});
