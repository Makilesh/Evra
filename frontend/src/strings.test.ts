import { describe, expect, it } from "vitest";
import type { AskFailureReason } from "@/bridge";
import { askFailureText, askRefusalText, canAskAgain, canRetry, noteFailureText } from "@/strings";

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

describe("asking", () => {
  const reasons: AskFailureReason[] = [
    "ollama_down",
    "model_missing",
    "cloud_model",
    "too_long",
    "cut_off",
    "invalid",
    "nothing_supported",
    "timeout",
    "no_transcript",
    "llm_error",
    "interrupted",
  ];

  it("explains a failed question in answer words, sharing the Ollama texts with the note", () => {
    expect(askFailureText("interrupted")).toBe("Evra closed before it answered. Ask again.");
    expect(askFailureText("too_long")).toBe("This question needs more room than the model's settings allow.");
    expect(askFailureText("cut_off")).toBe("The model ran out of room while answering.");
    expect(askFailureText("invalid")).toBe("The model didn't return a valid answer.");
    expect(askFailureText("timeout")).toBe("The model took too long to answer.");
    expect(askFailureText("ollama_down")).toBe(noteFailureText("ollama_down"));
    expect(askFailureText("model_missing")).toBe(noteFailureText("model_missing"));
    for (const reason of [...reasons, undefined]) {
      // "note model" names the setting; a note itself is never what failed here
      expect(askFailureText(reason)).not.toMatch(/\bnote\b(?! model)/i);
    }
  });

  it("says why a question was not asked", () => {
    expect(askRefusalText("invalid")).toBe("Type a question of up to 500 characters.");
    expect(askRefusalText("busy")).toBe("Evra is still answering the last question.");
    expect(askRefusalText("recording")).toBe("You can ask once the recording ends.");
    expect(askRefusalText("no_transcript")).toBe("There's no transcript to ask about yet.");
  });

  it("offers to ask again only where asking again can help", () => {
    expect(canAskAgain("too_long")).toBe(false);
    expect(canAskAgain("no_transcript")).toBe(false);
    for (const reason of reasons.filter((r) => r !== "too_long" && r !== "no_transcript")) {
      expect(canAskAgain(reason)).toBe(true);
    }
    expect(canAskAgain(undefined)).toBe(true);
  });
});
