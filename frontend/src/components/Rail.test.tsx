import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { MicList, RecordingState } from "@/bridge";
import { Rail } from "@/components/Rail";

const MICS: MicList = {
  default: "Headset (realme Buds Air7)",
  mics: ["Headset (realme Buds Air7)", "Microphone Array (Realtek(R) Audio)"],
  chosen: "",
};

function rail(recording: RecordingState, extra: Partial<Parameters<typeof Rail>[0]> = {}) {
  const props = {
    appName: "Evra",
    recording,
    levels: { you: 0.5, them: 0.25 },
    mics: MICS,
    startError: null,
    onStart: vi.fn(),
    onStop: vi.fn(),
    onDismissError: vi.fn(),
    onRefreshMics: vi.fn(),
    settingsOpen: false,
    onOpenSettings: vi.fn(),
    ...extra,
  };
  render(<Rail {...props} />);
  return props;
}

it("opens Settings from the foot of the rail", async () => {
  const props = rail({ state: "idle" });
  expect(screen.getByRole("button", { name: "Settings" })).not.toHaveAttribute("aria-current");
  await userEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(props.onOpenSettings).toHaveBeenCalled();
});

it("marks Settings while it is the open page", () => {
  rail({ state: "idle" }, { settingsOpen: true });
  expect(screen.getByRole("button", { name: "Settings" })).toHaveAttribute("aria-current", "page");
});

it("shows the app name and that everything stays on this PC", () => {
  rail({ state: "idle" });
  expect(screen.getByText("Evra")).toBeInTheDocument();
  expect(screen.getByText("Everything stays on this PC")).toBeInTheDocument();
});

it("records with the chosen microphone", async () => {
  const props = rail({ state: "idle" });
  expect(screen.getByRole("option", { name: "Windows default (Headset (realme Buds Air7))" })).toBeInTheDocument();
  await userEvent.selectOptions(
    screen.getByRole("combobox", { name: "Microphone" }),
    "Microphone Array (Realtek(R) Audio)",
  );
  await userEvent.click(screen.getByRole("button", { name: "Record" }));
  expect(props.onStart).toHaveBeenCalledWith("Microphone Array (Realtek(R) Audio)");
});

it("keeps a remembered mic that is not connected visible", () => {
  rail({ state: "idle" }, { mics: { ...MICS, chosen: "Headset (Mivi Roam 2)" } });
  expect(screen.getByRole("combobox", { name: "Microphone" })).toHaveValue("Headset (Mivi Roam 2)");
  expect(screen.getByRole("option", { name: "Headset (Mivi Roam 2) (not connected)" })).toBeInTheDocument();
});

it("shows Stop, the time and both levels while recording", async () => {
  const props = rail({ state: "recording", meeting_id: "m", started_at: 1_000_000 }, { now: () => 1_065_000 });
  expect(screen.getByRole("timer", { name: "Recording time" })).toHaveTextContent("01:05");
  expect(screen.getByRole("meter", { name: "You" })).toHaveAttribute("aria-valuenow", "0.5");
  expect(screen.getByRole("meter", { name: "Them" })).toHaveAttribute("aria-valuenow", "0.25");
  expect(screen.getByRole("combobox", { name: "Microphone" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Stop" }));
  expect(props.onStop).toHaveBeenCalled();
});

it.each([
  ["loading", "Loading…"],
  ["stopping", "Stopping…"],
  ["processing", "Writing note…"],
] as const)("is busy while %s", (state, label) => {
  rail({ state });
  expect(screen.getByRole("button", { name: label })).toBeDisabled();
});

it("shows why recording could not start, with its fix, until dismissed", async () => {
  const props = rail(
    { state: "idle" },
    { startError: { error: "microphone 'Headset' is not connected", hint: "Pick the microphone again." } },
  );
  const alert = screen.getByRole("alert");
  expect(alert).toHaveTextContent("microphone 'Headset' is not connected");
  expect(alert).toHaveTextContent("Pick the microphone again.");
  await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
  expect(props.onDismissError).toHaveBeenCalled();
});

it("lists the microphones again when the picker is opened", async () => {
  const props = rail({ state: "idle" });
  await userEvent.click(screen.getByRole("combobox", { name: "Microphone" }));
  expect(props.onRefreshMics).toHaveBeenCalled();
});

it("places the meetings list inside the rail", () => {
  rail({ state: "idle" }, { children: <nav aria-label="Meetings" /> });
  expect(screen.getByRole("navigation", { name: "Meetings" })).toBeInTheDocument();
});
