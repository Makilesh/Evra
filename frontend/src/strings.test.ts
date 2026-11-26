import { describe, expect, it } from "vitest";
import { canRetry, noteFailureText } from "@/strings";

describe("cloud_model failure", () => {
  it("says what happened and what to do", () => {
    expect(noteFailureText("cloud_model")).toBe(
      "That model runs in Ollama's cloud. Evra only uses models on this PC: choose another note model in Settings.",
    );
  });

  it("cannot be retried", () => {
    expect(canRetry("cloud_model")).toBe(false);
    expect(canRetry("timeout")).toBe(true);
    expect(canRetry("too_long")).toBe(false);
  });
});
