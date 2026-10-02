import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { MicList, RecordingState } from "@/bridge";
import { TopBar } from "@/components/TopBar";

const MICS: MicList = {
  default: "Headset (realme Buds Air7)",
  mics: ["Headset (realme Buds Air7)", "Microphone Array (Realtek(R) Audio)"],
  chosen: "",
};

function bar(recording: RecordingState, extra: Partial<Parameters<typeof TopBar>[0]> = {}) {
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
    ...extra,
  };
  render(<TopBar {...props} />);
  return props;
}

it("records with the chosen microphone", async () => {
  const props = bar({ state: "idle" });
  expect(screen.getByRole("option", { name: "Windows default (Headset (realme Buds Air7))" })).toBeInTheDocument();
  await userEvent.selectOptions(
    screen.getByRole("combobox", { name: "Microphone" }),
    "Microphone Array (Realtek(R) Audio)",
  );
  await userEvent.click(screen.getByRole("button", { name: "Record" }));
  expect(props.onStart).toHaveBeenCalledWith("Microphone Array (Realtek(R) Audio)");
});

it("keeps a remembered mic that is not connected visible", () => {
  bar({ state: "idle" }, { mics: { ...MICS, chosen: "Headset (Mivi Roam 2)" } });
  expect(screen.getByRole("combobox", { name: "Microphone" })).toHaveValue("Headset (Mivi Roam 2)");
  expect(screen.getByRole("option", { name: "Headset (Mivi Roam 2) (not connected)" })).toBeInTheDocument();
});

it("shows Stop, the time and both levels while recording", async () => {
  const props = bar({ state: "recording", meeting_id: "m", started_at: 1_000_000 }, { now: () => 1_065_000 });
  expect(screen.getByLabelText("Recording time")).toHaveTextContent("01:05");
  expect(screen.getByLabelText("You")).toHaveAttribute("aria-valuenow", "0.5");
  expect(screen.getByLabelText("Them")).toHaveAttribute("aria-valuenow", "0.25");
  expect(screen.getByRole("combobox", { name: "Microphone" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Stop" }));
  expect(props.onStop).toHaveBeenCalled();
});

it.each([
  ["loading", "Loading…"],
  ["stopping", "Stopping…"],
  ["processing", "Writing note…"],
] as const)("is busy while %s", (state, label) => {
  bar({ state });
  expect(screen.getByRole("button", { name: label })).toBeDisabled();
});

it("shows why recording could not start, with its fix, until dismissed", async () => {
  const props = bar(
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
  const props = bar({ state: "idle" });
  await userEvent.click(screen.getByRole("combobox", { name: "Microphone" }));
  expect(props.onRefreshMics).toHaveBeenCalled();
});
