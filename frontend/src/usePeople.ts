// The people the owner has named, who each 1:1 was with, and the promises across the 1:1s (Plan C).
// useEvra composes it: the people and the promises live here, a meeting's "with" lands in
// useEvra's state through `onLinked`, and a record's ticks show here through `showPromiseStatus`.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getApi,
  onEvent,
  type ItemStatus,
  type MeetingDetail,
  type MeetingSummary,
  type NameRefusal,
  type NameReply,
  type OpenPromise,
  type Person,
  type PromiseLists,
  type Utterance,
  type WithReply,
} from "@/bridge";
import { strings } from "@/strings";

/** Why who a 1:1 was with didn't change: Python refused the name, or couldn't be asked. */
export type WithRefusal = "reserved" | "invalid" | "failed";

/** Why a person kept their name. */
export type RenameRefusal = NameRefusal | "failed";

/** A ticked promise shows Done, with Undo, this long before it leaves the page. */
const UNDO_MS = 5_000;

export type Direction = keyof PromiseLists;

/** A promise as the window shows it: Python's, with the status the window last gave it. */
export interface ShownPromise {
  promise: OpenPromise;
  status: ItemStatus;
}

export type ShownPromises = Record<Direction, ShownPromise[]>;

/** A promise the window changed lately. It keeps its place on the page, by id, until Python's list
 *  has been read since its last save, and a Done one until its Undo time ends as well. */
interface Held {
  promise: OpenPromise;
  direction: Direction;
  /** Its place in its list when the window first changed it. */
  index: number;
  status: ItemStatus;
  /** The read of Python's list that decides for it once shown; none while a save runs. */
  read: number;
  /** When a Done one's Undo time ends (epoch ms). */
  undoEnds: number;
}

interface PromiseState {
  /** As Python last listed them; null until the first read answers. */
  listed: PromiseLists | null;
  /** The newest read shown: an older read that answers later is dropped. */
  read: number;
  held: Record<string, Held>;
}

/** A promise Python lists, as the window would first hold it. */
function located(listed: PromiseLists | null, id: string): Held | undefined {
  if (!listed) return undefined;
  for (const direction of ["you", "them"] as const) {
    const index = listed[direction].findIndex((p) => p.id === id);
    if (index >= 0) return { promise: listed[direction][index], direction, index, status: "open", read: 0, undoEnds: 0 };
  }
  return undefined;
}

/** The state without the held promises Python's list now decides for. */
function released(s: PromiseState, now: number): PromiseState {
  const kept = Object.entries(s.held).filter(([, h]) => s.read < h.read || (h.status === "done" && now < h.undoEnds));
  return kept.length === Object.keys(s.held).length ? s : { ...s, held: Object.fromEntries(kept) };
}

/** Python's lists with the window's changes laid over them: a held promise keeps its place even
 *  once Python no longer lists it, and one dismissed leaves. */
function shownPromises(listed: PromiseLists, held: Record<string, Held>): ShownPromises {
  const shown = (direction: Direction): ShownPromise[] => {
    const rows = listed[direction].map((promise) => ({ promise, status: held[promise.id]?.status ?? "open" }));
    const unlisted = Object.values(held)
      .filter((h) => h.direction === direction && !listed[direction].some((p) => p.id === h.promise.id))
      .sort((a, b) => a.index - b.index);
    for (const h of unlisted) rows.splice(Math.min(h.index, rows.length), 0, { promise: h.promise, status: h.status });
    return rows.filter((row) => row.status !== "dismissed");
  };
  return { you: shown("you"), them: shown("them") };
}

/** A line from the other side of the call names who the 1:1 was with, as Python labels them. */
export function spokenBy(utterance: Utterance, person: Person | null): Utterance {
  return utterance.channel === 1 ? { ...utterance, speaker: person?.name ?? strings.them } : utterance;
}

interface Shown {
  meetings: MeetingSummary[];
  detail: MeetingDetail | null;
}

/** The meeting list and the open meeting with who a 1:1 was with, at once: the header and the
 *  transcript name them. Its records' names come with the meeting read again. */
export function withMeetingPerson<S extends Shown>(s: S, meetingId: string, person: Person | null): S {
  const with_name = person?.name ?? null;
  const meetings = s.meetings.map((m) => (m.id === meetingId ? { ...m, with_name } : m));
  const open = s.detail;
  if (open?.meeting.id !== meetingId) return { ...s, meetings };
  const detail: MeetingDetail = {
    ...open,
    meeting: { ...open.meeting, with_name },
    with: person,
    utterances: open.utterances.map((u) => spokenBy(u, person)),
  };
  return { ...s, meetings, detail };
}

export function usePeople(onLinked: (meetingId: string, person: Person | null) => void) {
  const [people, setPeople] = useState<Person[]>([]);

  const refreshPeople = useCallback(async () => {
    try {
      const listed = await (await getApi()).list_people();
      setPeople(listed);
    } catch {
      // the suggestions stay as they were
    }
  }, []);

  useEffect(() => {
    let alive = true;
    getApi()
      .then((api) => api.list_people())
      .then((listed) => {
        if (alive) setPeople(listed);
      })
      .catch(() => {
        // no suggestions until the next change lists them
      });
    return () => {
      alive = false;
    };
  }, []);

  // Who a 1:1 was with, by name: Python finds the person (whatever the case) or makes one. An
  // empty name says no one. Null when it was said.
  const setMeetingPerson = useCallback(
    async (meetingId: string, name: string): Promise<WithRefusal | null> => {
      let reply: WithReply;
      try {
        reply = await (await getApi()).set_meeting_person(meetingId, name);
      } catch {
        return "failed";
      }
      if (!reply.ok) return reply.reason ?? "failed";
      onLinked(meetingId, reply.with ?? null);
      void refreshPeople(); // a new name is a new person
      return null;
    },
    [onLinked, refreshPeople],
  );

  // A person's new name; "taken" when someone else has it. Null when renamed.
  const renamePerson = useCallback(
    async (personId: string, name: string): Promise<RenameRefusal | null> => {
      let reply: NameReply;
      try {
        reply = await (await getApi()).rename_person(personId, name);
      } catch {
        return "failed";
      }
      if (!reply.ok) return reply.reason ?? "failed";
      void refreshPeople();
      return null;
    },
    [refreshPeople],
  );

  const [promised, setPromised] = useState<PromiseState>({ listed: null, read: 0, held: {} });
  const asked = useRef(0); // reads of the promises asked for so far
  // The promises as last shown, so a tick finds the status it starts from.
  const shown = useRef(promised);
  useEffect(() => {
    shown.current = promised;
  }, [promised]);

  // Python's list again. Reads can answer out of order, so only a newer one than shown lands.
  const refreshPromises = useCallback(async () => {
    const read = ++asked.current;
    let listed: PromiseLists;
    try {
      listed = await (await getApi()).list_promises();
    } catch {
      return; // the page keeps what it shows; the next change reads again
    }
    const now = Date.now();
    setPromised((s) => (read > s.read ? released({ ...s, listed, read }, now) : s));
  }, []);

  useEffect(() => {
    void refreshPromises();
    const offs = [
      onEvent("promises.changed", () => void refreshPromises()),
      onEvent("meeting.renamed", () => void refreshPromises()), // a promise names its meeting
    ];
    return () => offs.forEach((off) => off());
  }, [refreshPromises]);

  // When a Done row's Undo time ends, Python's list decides for it.
  useEffect(() => {
    const now = Date.now();
    const ends = Object.values(promised.held)
      .filter((h) => h.status === "done" && h.undoEnds > now)
      .map((h) => h.undoEnds);
    if (ends.length === 0) return;
    const timer = window.setTimeout(() => setPromised((s) => released(s, Date.now())), Math.min(...ends) - now);
    return () => window.clearTimeout(timer);
  }, [promised.held]);

  // The status a promise shows, for a tick to start from; undefined for one the page doesn't have.
  const promiseStatus = useCallback((id: string): ItemStatus | undefined => {
    const { held, listed } = shown.current;
    return held[id]?.status ?? located(listed, id)?.status;
  }, []);

  // A tick on a promise, from useEvra's one tick queue: shown at once (`saved` false), then with
  // the status Python last confirmed once its saves are answered (`saved` true). It keeps its
  // place until Python's list has been read again after that, and ticked done, for UNDO_MS.
  const showPromiseStatus = useCallback(
    (id: string, status: ItemStatus, saved: boolean) => {
      if (promiseStatus(id) === undefined) return; // a record of the open meeting alone
      const now = Date.now();
      const read = saved ? asked.current + 1 : Number.POSITIVE_INFINITY; // the read just below
      setPromised((s) => {
        const known = s.held[id] ?? located(s.listed, id);
        if (!known) return s;
        const undoEnds = status !== "done" ? 0 : known.status === "done" ? known.undoEnds : now + UNDO_MS;
        return released({ ...s, held: { ...s.held, [id]: { ...known, status, read, undoEnds } } }, now);
      });
      if (saved) void refreshPromises();
    },
    [promiseStatus, refreshPromises],
  );

  const promises = useMemo(() => promised.listed && shownPromises(promised.listed, promised.held), [promised]);
  const openPromises = promises && [...promises.you, ...promises.them].filter((row) => row.status === "open").length;

  return {
    people,
    refreshPeople,
    setMeetingPerson,
    renamePerson,
    /** Null until Python has listed them. */
    promises,
    /** How many the page shows open (the rail's count); null until listed. */
    openPromises,
    refreshPromises,
    promiseStatus,
    showPromiseStatus,
  };
}
