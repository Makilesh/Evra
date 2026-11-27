// The people the owner has named and who each 1:1 was with (Plan C). useEvra composes it: the
// people list lives here, and a meeting's "with" lands in useEvra's state through `onLinked`.
import { useCallback, useEffect, useState } from "react";
import {
  getApi,
  type MeetingDetail,
  type MeetingSummary,
  type NameRefusal,
  type NameReply,
  type Person,
  type Utterance,
  type WithReply,
} from "@/bridge";
import { strings } from "@/strings";

/** Why who a 1:1 was with didn't change: Python refused the name, or couldn't be asked. */
export type WithRefusal = "reserved" | "invalid" | "failed";

/** Why a person kept their name. */
export type RenameRefusal = NameRefusal | "failed";

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

  return { people, refreshPeople, setMeetingPerson, renamePerson };
}
