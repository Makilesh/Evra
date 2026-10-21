import { vi } from "vitest";
import type { EvraApi, MeetingDetail, MeetingSummary } from "@/bridge";

export const MEETING: MeetingSummary = {
  id: "m1",
  title: "Weekly 1:1",
  started_at: new Date(2026, 8, 28, 13, 51).getTime(),
  duration_ms: 720_000,
  state: "ready",
  has_note: true,
};

export const DETAIL: MeetingDetail = {
  meeting: MEETING,
  utterances: [
    { id: "u1", channel: 1, speaker: "Them", start_ms: 65_000, end_ms: 70_000, text: "Marketing wants October 14." },
    { id: "u2", channel: 0, speaker: "You", start_ms: 110_000, end_ms: 114_000, text: "I'll send the proposal by Thursday." },
  ],
  note: {
    model: "gemma4:12b",
    sections: [
      {
        id: "summary",
        title: "Summary",
        blocks: [{ text: "Launch moves to October 14.", citations: [{ utterance_id: "u1", start_ms: 65_000 }] }],
      },
      {
        id: "action_items",
        title: "Action items",
        blocks: [
          { text: "You: send the proposal by Thursday.", citations: [{ utterance_id: "u2", start_ms: 110_000 }] },
        ],
      },
    ],
  },
};

export function makeFakeApi(overrides: Partial<EvraApi> = {}): EvraApi {
  return {
    ping: vi.fn(async (message: string) => ({ reply: `pong: ${message}` })),
    app_info: vi.fn(async () => ({ name: "Evra", version: "0.1.0" })),
    request_hello: vi.fn(async () => null),
    list_meetings: vi.fn(async () => [MEETING]),
    get_meeting: vi.fn(async (id: string) => (id === MEETING.id ? DETAIL : null)),
    list_mics: vi.fn(async () => ({
      default: "Headset (realme Buds Air7)",
      mics: ["Headset (realme Buds Air7)", "Microphone Array (Realtek(R) Audio)"],
      chosen: "",
    })),
    start_recording: vi.fn(async () => ({ ok: true, meeting_id: "m2" })),
    stop_recording: vi.fn(async () => ({ ok: true })),
    write_note: vi.fn(async () => ({ ok: true })),
    rename_meeting: vi.fn(async () => ({ ok: true })),
    recording_state: vi.fn(async () => ({ state: "idle" as const })),
    ...overrides,
  };
}
