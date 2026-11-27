import { describe, expect, it } from "vitest";
import type { AskFailureReason, BriefFailureReason } from "@/bridge";
import {
  askFailureText,
  askRefusalText,
  briefFailureText,
  canAskAgain,
  canRetry,
  noteFailureText,
  strings,
} from "@/strings";

describe("cloud_model failure", () => {
  it("says what happened and what to do", () => {
    expect(noteFailureText("cloud_model")).toBe(
      "That model runs in Ollama's cloud. Evra only uses models on this PC: choose another note model in Settings.",
    );
  });

  it("can be retried once another model is chosen", () => {
    expect(canRetry("cloud_model")).toBe(true); // the owner picks another model, then retries
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
    expect(askFailureText("model_missing")).toBe(
      "The note model isn't installed in Ollama. Choose another in Settings, or install it with ollama pull.",
    );
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

describe("a meeting too long for a note", () => {
  it("says so and what the owner can still do, without Retry", () => {
    expect(noteFailureText("too_long")).toBe("This meeting is too long for a note. You can still ask about it.");
    expect(canRetry("too_long")).toBe(false);
  });
});

describe("note stages", () => {
  it("names the part of a long call being read, then the combining", () => {
    expect(strings.stages("part:2:6")).toBe("Reading part 2 of 6…");
    expect(strings.stages("part:1:1")).toBe("Reading part 1 of 1…");
    expect(strings.stages("combining")).toBe("Putting the note together…");
    expect(strings.stages("linking")).toBe("Linking your notes…");
    expect(strings.stages("writing")).toBe("Writing note…");
    expect(strings.stages("items")).toBe("Listing action items…");
    expect(strings.stages("part:x:2")).toBeUndefined();
    expect(strings.stages("something new")).toBeUndefined();
  });
});

describe("people and briefs", () => {
  it("counts a person's open promises both ways, leaving out a side with none", () => {
    expect(strings.promisedCounts(2, 1)).toBe("You promised 2 · They promised 1");
    expect(strings.promisedCounts(0, 3)).toBe("They promised 3");
    expect(strings.promisedCounts(1, 0)).toBe("You promised 1");
    expect(strings.promisedCounts(0, 0)).toBe("");
  });

  it("explains a failed brief in brief words, sharing the Ollama texts with the note", () => {
    expect(briefFailureText("cut_off")).toBe("The model ran out of room while writing the brief.");
    expect(briefFailureText("invalid")).toBe("The model didn't return a valid brief.");
    expect(briefFailureText("timeout")).toBe("The model took too long to write the brief.");
    expect(briefFailureText("ollama_down")).toBe(noteFailureText("ollama_down"));
    expect(briefFailureText("cloud_model")).toBe(noteFailureText("cloud_model"));
    expect(briefFailureText("model_missing")).toBe(askFailureText("model_missing"));
    const reasons: BriefFailureReason[] = ["too_long", "nothing_supported", "no_transcript", "llm_error", "unknown"];
    for (const reason of [...reasons, undefined]) {
      expect(briefFailureText(reason)).toMatch(/brief/);
    }
  });
});
