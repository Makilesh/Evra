// A person's page and their prep brief (Plan C Task 3), beside usePeople, which composes it: the
// page as Python read it for the person whose page is open, how each person's last brief went,
// and renaming and forgetting them. Their open promises are usePeople's one list (RC7).
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getApi,
  onEvent,
  type BriefFailureReason,
  type BriefRefusal,
  type BriefReply,
  type BriefUpdated,
  type NameReply,
  type PersonPage,
} from "@/bridge";
import type { RenameRefusal } from "@/usePeople";

/** How the last brief asked for this session went: being written, none of its points could be
 *  checked, or it failed, each until the next is asked for; or Python didn't start it ("failed"
 *  when it couldn't be asked), until the person's page opens again or the cause ends (RC14): a
 *  note job for "recording" and "note", any brief for "busy". A brief written lands on the page
 *  instead. */
export type BriefStatus =
  | { state: "writing" }
  | { state: "unchecked" }
  | { state: "failed"; reason: BriefFailureReason }
  | { state: "refused"; reason: BriefRefusal | "failed" };

function without<T>(map: Record<string, T>, key: string): Record<string, T> {
  const rest = { ...map };
  delete rest[key];
  return rest;
}

/** Everyone's statuses but the refusals for these reasons; the same map when there are none. */
function withoutRefusals(
  briefs: Record<string, BriefStatus>,
  reasons: (BriefRefusal | "failed")[],
): Record<string, BriefStatus> {
  const kept = Object.entries(briefs).filter(([, b]) => b.state !== "refused" || !reasons.includes(b.reason));
  return kept.length === Object.keys(briefs).length ? briefs : Object.fromEntries(kept);
}

export function usePersonPage(refreshPeople: () => Promise<void>, refreshPromises: () => Promise<void>) {
  const [personPage, setPersonPage] = useState<PersonPage | null>(null);
  const [briefs, setBriefs] = useState<Record<string, BriefStatus>>({});
  const open = useRef<string | null>(null); // whose page the window shows
  const reads = useRef(0);

  // Python's page for the person; only the newest read lands, and only while their page is open.
  const loadPersonPage = useCallback(async (personId: string) => {
    const read = ++reads.current;
    let page: PersonPage | null;
    try {
      page = await (await getApi()).person_page(personId);
    } catch {
      return; // the page keeps what it shows; opening it again reads again
    }
    if (read === reads.current && open.current === personId) setPersonPage(page);
  }, []);

  // The window shows this person's page now (null: no one's), read afresh. Opened again, it no
  // longer says why the last press was refused.
  const openPersonPage = useCallback(
    (personId: string | null) => {
      if (open.current !== personId) setPersonPage(null);
      open.current = personId;
      if (!personId) return;
      setBriefs((s) => (s[personId]?.state === "refused" ? without(s, personId) : s));
      void loadPersonPage(personId);
    },
    [loadPersonPage],
  );

  useEffect(() => {
    const reload = () => {
      if (open.current) void loadPersonPage(open.current);
    };
    // A note job ended, with its note or without: a brief that waited for it can be asked for.
    const noteJobEnded = () => setBriefs((s) => withoutRefusals(s, ["recording", "note"]));
    const offs = [
      // A brief ended, so the slot is free again. It may beat write_brief's own reply; that reply
      // then changes nothing.
      onEvent("brief.updated", (payload) => {
        const { person_id, state, reason, brief } = payload as BriefUpdated;
        setBriefs((before) => {
          const s = withoutRefusals(before, ["busy"]);
          if (state === "written") return without(s, person_id);
          const status: BriefStatus = state === "failed" ? { state, reason: reason ?? "llm_error" } : { state };
          return { ...s, [person_id]: status };
        });
        if (state === "written" && brief) {
          setPersonPage((page) => (page?.person.id === person_id ? { ...page, brief } : page));
        }
      }),
      onEvent("note.ready", () => {
        noteJobEnded();
        reload(); // a 1:1 of theirs may have its note now: last time, the list
      }),
      onEvent("note.failed", noteJobEnded),
      onEvent("meeting.renamed", reload), // the page names their meetings
    ];
    return () => offs.forEach((off) => off());
  }, [loadPersonPage]);

  // Ask for the person's brief: shown as being written at once; it arrives as `brief.updated`.
  const writeBrief = useCallback(async (personId: string) => {
    setBriefs((s) => ({ ...s, [personId]: { state: "writing" } }));
    let reply: BriefReply;
    try {
      reply = await (await getApi()).write_brief(personId);
    } catch {
      reply = { ok: false };
    }
    if (!reply.ok) {
      const refused: BriefStatus = { state: "refused", reason: reply.reason ?? "failed" };
      setBriefs((s) => ({ ...s, [personId]: refused }));
    }
  }, []);

  // A person's new name; "taken" when someone else has it. Null when renamed: every list that
  // shows them is read again (a promise names who its 1:1 was with), and so is their page.
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
      void refreshPromises();
      if (open.current === personId) void loadPersonPage(personId);
      return null;
    },
    [refreshPeople, refreshPromises, loadPersonPage],
  );

  // Forget a person (D14): their meetings say "Them" again and their brief is deleted. True once
  // done; the lists are read again.
  const forgetPerson = useCallback(
    async (personId: string): Promise<boolean> => {
      let ok = false;
      try {
        ok = (await (await getApi()).remove_person(personId)).ok;
      } catch {
        // not forgotten: the page says so
      }
      if (!ok) return false;
      if (open.current === personId) openPersonPage(null);
      setBriefs((s) => without(s, personId));
      void refreshPeople();
      void refreshPromises();
      return true;
    },
    [refreshPeople, refreshPromises, openPersonPage],
  );

  return {
    /** The open person's page as Python read it; null while it is read. */
    personPage,
    openPersonPage,
    /** Each person's last brief asked for, while it runs or if it didn't land. */
    briefs,
    writeBrief,
    renamePerson,
    forgetPerson,
  };
}
