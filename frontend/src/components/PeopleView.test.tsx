import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it } from "vitest";
import App from "@/App";
import { setApiForTests } from "@/bridge";
import { dayLabel } from "@/format";
import { makeFakeApi } from "@/test/fakeApi";
import { HIRING, WEEKLY, peopleApi } from "@/test/fakePeople";

afterEach(() => setApiForTests(null));

async function openPeople() {
  await userEvent.click(await screen.findByRole("button", { name: "People" }));
  return screen.findByRole("heading", { level: 1, name: "People" });
}

it("lists people", async () => {
  const api = peopleApi();
  setApiForTests(api);
  render(<App />);
  await screen.findByText("Launch moves to October 14."); // the newest meeting opens first
  await openPeople();
  expect(screen.getByRole("button", { name: "People" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("button", { name: /^Weekly 1:1/ })).not.toHaveAttribute("aria-current");
  // by name: when their last 1:1 was, and their open promises both ways
  const priya = await screen.findByRole("button", { name: /^Priya/ });
  expect(priya).toHaveTextContent(`Last 1:1 ${dayLabel(WEEKLY.started_at, Date.now())}`);
  expect(priya).toHaveTextContent("You promised 1 · They promised 1");
  const sam = screen.getByRole("button", { name: /^Sam Lee/ });
  expect(sam).toHaveTextContent(`Last 1:1 ${dayLabel(HIRING.started_at, Date.now())}`);
  expect(sam).toHaveTextContent("You promised 1");
  expect(sam).not.toHaveTextContent("They promised");
  expect(priya.compareDocumentPosition(sam) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(api.list_promises).toHaveBeenCalledTimes(2); // on starting, and again as the page opened
  expect(priya.closest(".overflow-y-auto")).not.toBeNull(); // the page has its own scroller
  // a person's page opens from their row, still under People
  await userEvent.click(priya);
  expect(await screen.findByRole("heading", { level: 1, name: "Priya" })).toHaveFocus();
  expect(api.person_page).toHaveBeenCalledWith("p1");
  expect(screen.getByRole("button", { name: "People" })).toHaveAttribute("aria-current", "page");
  // and the rail's link goes back to everyone
  await openPeople();
  expect(screen.getByRole("button", { name: /^Sam Lee/ })).toBeInTheDocument();
});

it("says how to name someone when there is no one yet", async () => {
  setApiForTests(makeFakeApi());
  render(<App />);
  await openPeople();
  expect(screen.getByText("No people yet. Say who a 1:1 was with from its page.")).toBeInTheDocument();
});
