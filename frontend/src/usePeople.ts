// The people the owner has named, who each 1:1 was with, and the promises across the 1:1s (Plan C).
// useEvra composes it: the people and the promises live here, a meeting's "with" lands in
// useEvra's state through `onLinked`, and a record's ticks show here through `showPromiseStatus`.
// A person's page and their brief are usePersonPage's, composed here.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getApi,
  onEvent,
  type ItemStatus,
  type MeetingDetail,
  type MeetingSummary,
  type NameRefusal,
  type OpenPromise,
  type Person,
  type PersonSummary,
  type PromiseLists,
  type Utterance,
  type WithReply,
} from "@/bridge";
import { strings } from "@/strings";
import { usePersonPage } from "@/usePersonPage";

/** Why who a 1:1 was with didn't change: Python refused the name, or couldn't be asked. */
export type WithRefusal = "reserved" | "invalid" | "failed";

/** Why a person kept their name. */
export type RenameRefusal = NameRefusal | "failed";

/** A promise ticked done, or set aside as not one, shows so with Undo this long before it leaves
 *  the page. */
const UNDO_MS = 5_000;

export type Direction = keyof PromiseLists;

/** A promise as the window shows it: Python's, with the status the window last gave it. */
export interface ShownPromise {
  promise: OpenPromise;
  status: ItemStatus;
}

export type ShownPromises = Record<Direction, ShownPromise[]>;

/** A promise the window changed lately. It stays on the page until Python's list has been read
 *  since its last save, and one done or set aside until its Undo time ends too. */
interface Held {
  promise: OpenPromise;
  direction: Direction;
  status: ItemStatus;
  /** The read of Python's list that decides for it once shown; none while a save runs. */
  read: number;
  /** When the Undo time of one done or set aside ends (epoch ms). */
  undoEnds: number;
}

interface PromiseState {
  /** As Python last listed them; null until the first read answers. */
  listed: PromiseLists | null;
  /** The newest read shown: an older read that answers later is dropped. */
  read: number;
  held: Record<string, Held>;
  /** Each list's promises in the order last shown, so a held one keeps its place among its
   *  neighbours while Python's list changes around it. */
  order: Record<Direction, string[]>;
  /** The newest read asked for failed (a page that shows nothing yet says so). */
  failed: boolean;
}

const DIRECTIONS: Direction[] = ["you", "them"];

/** A promise Python lists, as the window would first hold it. */
function located(listed: PromiseLists | null, id: string): Held | undefined {
  for (const direction of DIRECTIONS) {
    const promise = listed?.[direction].find((p) => p.id === id);
    if (promise) return { promise, direction, status: "open", read: 0, undoEnds: 0 };
  }
  return undefined;
}

/** A list's order after a change: a promise still listed or held keeps its place, and one Python
 *  newly lists goes in after the one Python lists before it. */
function arranged(order: string[], listed: OpenPromise[], held: Record<string, Held>): string[] {
  const ids = listed.map((p) => p.id);
  const next = order.filter((id) => ids.includes(id) || id in held);
  ids.forEach((id, i) => {
    if (!next.includes(id)) next.splice(i === 0 ? 0 : next.indexOf(ids[i - 1]) + 1, 0, id);
  });
  return next.length === order.length && next.every((id, i) => id === order[i]) ? order : next;
}

/** The state once the held promises Python's list now decides for are let go, with each list's
 *  order brought up to date. The same state when nothing changed. */
function settled(s: PromiseState, now: number): PromiseState {
  const kept = Object.entries(s.held).filter(([, h]) => s.read < h.read || (h.status !== "open" && now < h.undoEnds));
  const held = kept.length === Object.keys(s.held).length ? s.held : Object.fromEntries(kept);
  const listed = s.listed;
  const you = listed ? arranged(s.order.you, listed.you, held) : s.order.you;
  const them = listed ? arranged(s.order.them, listed.them, held) : s.order.them;
  const order = you === s.order.you && them === s.order.them ? s.order : { you, them };
  return held === s.held && order === s.order ? s : { ...s, held, order };
}

/** Each list in the order shown, with the window's changes laid over Python's: a held promise
 *  stays even once Python no longer lists it (ticked done, or set aside). */
function shownPromises(s: PromiseState): ShownPromises {
  const shown = (direction: Direction): ShownPromise[] =>
    s.order[direction].flatMap((id) => {
      const promise = s.listed?.[direction].find((p) => p.id === id) ?? s.held[id]?.promise;
      return promise ? [{ promise, status: s.held[id]?.status ?? "open" }] : [];
    });
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
  const [people, setPeople] = useState<PersonSummary[]>([]);

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

  const [promised, setPromised] = useState<PromiseState>({
    listed: null,
    read: 0,
    held: {},
    order: { you: [], them: [] },
    failed: false,
  });
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
      // the page keeps what it shows; the next change, or opening a page, reads again
      setPromised((s) => (read > s.read ? { ...s, failed: true } : s));
      return;
    }
    const now = Date.now();
    setPromised((s) => (read > s.read ? settled({ ...s, listed, read, failed: false }, now) : s));
  }, []);

  useEffect(() => {
    void refreshPromises();
    const offs = [
      onEvent("promises.changed", () => void refreshPromises()),
      onEvent("meeting.renamed", () => void refreshPromises()), // a promise names its meeting
    ];
    return () => offs.forEach((off) => off());
  }, [refreshPromises]);

  // When the Undo time of a row done or set aside ends, Python's list decides for it.
  useEffect(() => {
    const now = Date.now();
    const ends = Object.values(promised.held)
      .filter((h) => h.status !== "open" && h.undoEnds > now)
      .map((h) => h.undoEnds);
    if (ends.length === 0) return;
    const timer = window.setTimeout(() => setPromised((s) => settled(s, Date.now())), Math.min(...ends) - now);
    return () => window.clearTimeout(timer);
  }, [promised.held]);

  // The status a promise shows, for a tick to start from; undefined for one the page doesn't have.
  const promiseStatus = useCallback((id: string): ItemStatus | undefined => {
    const { held, listed } = shown.current;
    return held[id]?.status ?? located(listed, id)?.status;
  }, []);

  // A promise's status, from useEvra's one tick queue: shown at once (`saved` false), then as
  // Python last confirmed it once its saves are answered (`saved` true). It keeps its place until
  // Python's list has been read again after that; done or set aside, also for UNDO_MS from when it
  // first showed so.
  const showPromiseStatus = useCallback(
    (id: string, status: ItemStatus, saved: boolean) => {
      if (promiseStatus(id) === undefined) return; // a record of the open meeting alone
      const now = Date.now();
      const read = saved ? asked.current + 1 : Number.POSITIVE_INFINITY; // the read just below
      setPromised((s) => {
        const known = s.held[id] ?? located(s.listed, id);
        if (!known) return s;
        const undoEnds = status === "open" ? 0 : known.status === status ? known.undoEnds : now + UNDO_MS;
        return settled({ ...s, held: { ...s.held, [id]: { ...known, status, read, undoEnds } } }, now);
      });
      if (saved) void refreshPromises();
    },
    [promiseStatus, refreshPromises],
  );

  const promises = useMemo(() => promised.listed && shownPromises(promised), [promised]);
  const openPromises = promises && [...promises.you, ...promises.them].filter((row) => row.status === "open").length;
  const personPage = usePersonPage(refreshPeople, refreshPromises);

  return {
    people,
    refreshPeople,
    setMeetingPerson,
    /** Null until Python has listed them. */
    promises,
    /** Nothing listed yet, and the last read failed. */
    promisesUnread: promised.listed === null && promised.failed,
    /** How many the page shows open (the rail's count); null until listed. */
    openPromises,
    refreshPromises,
    promiseStatus,
    showPromiseStatus,
    ...personPage,
  };
}

/** The shown promises of the 1:1s with one person, both ways (RC7: one list in the window). */
export function promisesOf(promises: ShownPromises, personId: string): ShownPromises {
  const theirs = (rows: ShownPromise[]) => rows.filter((row) => row.promise.person?.id === personId);
  return { you: theirs(promises.you), them: theirs(promises.them) };
}
