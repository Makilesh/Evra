import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { NoteModels, SettingsInfo } from "@/bridge";
import { SettingsView } from "@/components/SettingsView";

const SETTINGS: SettingsInfo = {
  theme: "light",
  note_model: "gemma4:12b",
  default_note_model: "gemma4:12b",
  data_dir: "D:\\Evra\\.data\\data",
  version: "0.1.0",
};

function view(extra: Partial<Parameters<typeof SettingsView>[0]> = {}) {
  const props = {
    appName: "Evra",
    settings: SETTINGS,
    noteModels: { ok: true, models: ["gemma4:12b", "qwen3.5:9b"] } as NoteModels | null,
    error: "",
    onTheme: vi.fn(),
    onNoteModel: vi.fn(),
    onLoadModels: vi.fn(),
    onOpenFolder: vi.fn(async () => true),
    onClose: vi.fn(),
    ...extra,
  };
  return { props, ...render(<SettingsView {...props} />) };
}

it("opens with focus on its heading", () => {
  view();
  expect(screen.getByRole("heading", { level: 1, name: "Settings" })).toHaveFocus();
});

it("offers Light, Dark and Match Windows, with the current theme chosen", async () => {
  const { props } = view();
  expect(screen.getAllByRole("radio")).toHaveLength(3);
  expect(screen.getByRole("radio", { name: "Light" })).toBeChecked();
  expect(screen.getByRole("radio", { name: "Dark" })).not.toBeChecked();
  await userEvent.click(screen.getByRole("radio", { name: "Dark" }));
  expect(props.onTheme).toHaveBeenCalledWith("dark");
  await userEvent.click(screen.getByRole("radio", { name: "Match Windows" }));
  expect(props.onTheme).toHaveBeenCalledWith("system");
});

it("lists the models in Ollama, marks the recommended one and saves a choice", async () => {
  const { props } = view();
  expect(props.onLoadModels).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("option", { name: "gemma4:12b (recommended)" })).toBeInTheDocument();
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "Note model" }), "qwen3.5:9b");
  expect(props.onNoteModel).toHaveBeenCalledWith("qwen3.5:9b");
});

it("waits for Ollama before the model can be changed", () => {
  view({ noteModels: null });
  expect(screen.getByRole("combobox", { name: "Note model" })).toBeDisabled();
  expect(screen.getByText("Looking for models in Ollama…")).toBeInTheDocument();
});

it("says why the model can't be changed while Ollama is quiet, and checks again", async () => {
  const { props } = view({ noteModels: { ok: false, models: [] } });
  expect(screen.getByRole("combobox", { name: "Note model" })).toBeDisabled();
  expect(screen.getByText(/Ollama isn't answering/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Check again" }));
  expect(props.onLoadModels).toHaveBeenCalledTimes(2);
});

it("says how to install a note model that isn't in Ollama", () => {
  view({ noteModels: { ok: true, models: ["qwen3.5:9b"] } });
  expect(screen.getByText(/gemma4:12b isn't installed in Ollama/)).toHaveTextContent("ollama pull gemma4:12b");
});

it("shows where meetings are kept and opens the folder", async () => {
  const { props } = view();
  expect(screen.getByText("D:\\Evra\\.data\\data")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Open folder" }));
  expect(props.onOpenFolder).toHaveBeenCalled();
  expect(screen.queryByRole("alert")).toBeNull();
});

it("says when the folder couldn't be opened", async () => {
  view({ onOpenFolder: vi.fn(async () => false) });
  await userEvent.click(screen.getByRole("button", { name: "Open folder" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't open the folder.");
});

it("shows the version and closes", async () => {
  const { props } = view();
  expect(screen.getByText("Evra 0.1.0")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Close settings" }));
  expect(props.onClose).toHaveBeenCalled();
});

it("reports a change that couldn't be saved", () => {
  view({ error: "Couldn't save that change. It applies until Evra closes." });
  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't save that change.");
});
