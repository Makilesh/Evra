// Python's side of the People pages, for tests through <App/>: two people, their 1:1s, the
// promises across them with saved statuses, a person's page and renaming and forgetting them.
import { vi } from "vitest";
import type {
  Brief,
  EvraApi,
  ItemStatus,
  MeetingSummary,
  OpenPromise,
  Person,
  PersonPage,
  PersonSummary,
} from "@/bridge";
import { DETAIL, MEETING, makeFakeApi } from "@/test/fakeApi";

export const PRIYA: Person = { id: "p1", name: "Priya" };
export const SAM: Person = { id: "p2", name: "Sam Lee" };

export const WEEKLY: MeetingSummary = { ...MEETING, with_name: "Priya" }; // m1, Mon 28 Sept
export const BUDGET: MeetingSummary = {
  ...MEETING,
  id: "m2",
  title: "Budget check",
  started_at: new Date(2026, 8, 21, 10, 0).getTime(),
  with_name: "Priya",
};
export const HIRING: MeetingSummary = {
  ...MEETING,
  id: "m3",
  title: "Hiring sync",
  started_at: new Date(2026, 8, 25, 9, 0).getTime(),
  has_note: false,
  with_name: "Sam Lee",
};

const SEND: OpenPromise = {
  id: "i1",
  text: "Send the proposal",
  due: "by Thursday",
  owner: "You",
  meeting_id: "m1",
  meeting_title: "Weekly 1:1",
  started_at: WEEKLY.started_at,
  person: PRIYA,
  utterance_id: "u2",
  start_ms: 110_000,
};
const MARKETING: OpenPromise = {
  ...SEND,
  id: "i2",
  text: "Tell marketing about October 14",
  due: null,
  owner: "Them",
  utterance_id: "u1",
  start_ms: 65_000,
};
const LOOP: OpenPromise = {
  ...SEND,
  id: "i3",
  text: "Write up the interview loop",
  due: null,
  meeting_id: "m3",
  meeting_title: "Hiring sync",
  started_at: HIRING.started_at,
  person: SAM,
  utterance_id: null,
  start_ms: null,
};
const DECK: OpenPromise = { ...LOOP, id: "i4", text: "Share the deck", owner: "Them", person: null };
export const PROMISES = { SEND, MARKETING, LOOP, DECK };

export const BRIEF: Brief = {
  created_at: WEEKLY.started_at + 3_600_000,
  points: [
    { text: "You still owe Priya the proposal, due Thursday.", meetings: [{ id: "m1", title: "Weekly 1:1", started_at: WEEKLY.started_at }] },
    {
      text: "The contractor budget is twelve thousand dollars.",
      meetings: [
        { id: "m2", title: "Budget check", started_at: BUDGET.started_at },
        { id: "m1", title: "Weekly 1:1", started_at: WEEKLY.started_at },
      ],
    },
  ],
};

/** The bridge, with what it was asked kept in its own state. */
export function peopleApi(overrides: Partial<EvraApi> = {}): EvraApi {
  let people: Person[] = [PRIYA, SAM];
  const met: Record<string, number> = { p1: WEEKLY.started_at, p2: HIRING.started_at };
  const saved = new Map<string, ItemStatus>();
  const named = (p: OpenPromise) => {
    const person = p.person && people.find((q) => q.id === p.person?.id);
    return { ...p, person: person ?? null };
  };
  const open = (p: OpenPromise) => (saved.get(p.id) ?? "open") === "open";
  const page = (id: string): PersonPage | null => {
    const person = people.find((p) => p.id === id);
    if (!person) return null;
    if (id === SAM.id) return { person, last: null, brief: null, meetings: [{ ...HIRING, with_name: person.name }] };
    return {
      person,
      last: {
        meeting_id: "m1",
        title: "Weekly 1:1",
        started_at: WEEKLY.started_at,
        next_time: [{ text: "Mentoring a new hire: talk to Sam.", citations: [{ utterance_id: "u2", start_ms: 110_000 }] }],
        open_questions: [
          {
            text: "Can the API limit go to 500 requests a minute?",
            citations: [{ utterance_id: "u1", start_ms: 65_000 }],
            item: { id: "q1", kind: "open_question", status: "open", owner: null, due: null },
          },
        ],
      },
      brief: null,
      meetings: [WEEKLY, BUDGET].map((m) => ({ ...m, with_name: person.name })),
    };
  };
  return makeFakeApi({
    list_meetings: vi.fn(async () => [WEEKLY, HIRING, BUDGET]),
    get_meeting: vi.fn(async (id: string) => {
      const meeting = [WEEKLY, BUDGET, HIRING].find((m) => m.id === id) ?? WEEKLY;
      return { ...DETAIL, meeting };
    }),
    list_people: vi.fn(async (): Promise<PersonSummary[]> => people.map((p) => ({ ...p, last_met: met[p.id] ?? null }))),
    list_promises: vi.fn(async () => {
      const rows = [SEND, MARKETING, LOOP, DECK].filter(open).map(named);
      return { you: rows.filter((p) => p.owner === "You"), them: rows.filter((p) => p.owner === "Them") };
    }),
    set_item_status: vi.fn(async (id: string, status: ItemStatus) => {
      saved.set(id, status);
      return { ok: true };
    }),
    person_page: vi.fn(async (id: string) => page(id)),
    rename_person: vi.fn(async (id: string, name: string) => {
      const tidy = name.trim().replace(/\s+/g, " ");
      if (tidy.replace(/ /g, "").toLowerCase() === "you") return { ok: false, reason: "reserved" as const };
      if (people.some((p) => p.id !== id && p.name.toLowerCase() === tidy.toLowerCase())) {
        return { ok: false, reason: "taken" as const };
      }
      people = people.map((p) => (p.id === id ? { ...p, name: tidy } : p));
      return { ok: true };
    }),
    remove_person: vi.fn(async (id: string) => {
      const known = people.some((p) => p.id === id);
      people = people.filter((p) => p.id !== id);
      return { ok: known };
    }),
    ...overrides,
  });
}
