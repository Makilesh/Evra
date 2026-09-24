import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it } from "vitest";
import App from "@/App";
import { emit, setApiForTests, type EvraApi } from "@/bridge";

const fakeApi: EvraApi = {
  ping: async (m) => ({ reply: `pong: ${m}` }),
  app_info: async () => ({ name: "Evra", version: "0.1.0" }),
  request_hello: async () => null,
};

afterEach(() => setApiForTests(null));

it("shows the app name and version from Python", async () => {
  setApiForTests(fakeApi);
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Evra 0.1.0" })).toBeInTheDocument();
});

it("pings Python and shows the reply", async () => {
  setApiForTests(fakeApi);
  render(<App />);
  await userEvent.click(screen.getByRole("button", { name: "Ping Python" }));
  expect(await screen.findByRole("status")).toHaveTextContent("pong: hello");
});

it("shows events pushed from Python", async () => {
  setApiForTests(fakeApi);
  render(<App />);
  await screen.findByRole("heading", { name: "Evra 0.1.0" });
  act(() => emit("app.hello", { message: "Python is connected" }));
  expect(screen.getByTestId("last-event")).toHaveTextContent("Python is connected");
});

it("shows an error when the bridge is unavailable", async () => {
  setApiForTests({
    ...fakeApi,
    app_info: async () => {
      throw new Error("boom");
    },
  });
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent("boom");
});
