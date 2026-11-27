import { type ChangeEvent, type KeyboardEvent, useEffect, useId, useRef, useState } from "react";
import { strings } from "@/strings";

interface InlineEditOptions<R> {
  /** What the input starts from each time it opens. */
  initial: string;
  /** Saves the trimmed draft: null once saved, else why not. A save that throws reads as not
   *  saved. */
  save: (value: string) => Promise<R | null>;
  /** The caller's sentence for one of its refusals; null where it has none (then: not saved). */
  refusalText: (reason: R) => string | null;
  /** An empty draft is a save (who a 1:1 was with: no one); otherwise it asks for a name. */
  allowEmpty?: boolean;
}

/** One in-place name editor: a button opens an input; Enter saves the trimmed draft and Escape
 *  cancels, either putting the focus back on the button; a blur closes it. Every refusal says why
 *  under the input, which stays open (`aria-invalid`): the caller's words, else "type a name" for
 *  an empty one, else "couldn't save" (a refusal it has no words for, or a save that threw). */
export function useInlineEdit<R>({ initial, save, refusalText, allowEmpty = false }: InlineEditOptions<R>) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(initial);
  const [refusal, setRefusal] = useState("");
  const button = useRef<HTMLButtonElement>(null); // opens the input, and gets the focus back
  const open = useRef(false); // the input, for a reply that lands after it closed
  const saving = useRef(false);
  const refocus = useRef(false);
  const refusalId = useId();

  useEffect(() => {
    if (editing || !refocus.current) return;
    refocus.current = false;
    button.current?.focus();
  }, [editing]);

  function begin() {
    open.current = true;
    setDraft(initial);
    setRefusal("");
    setEditing(true);
  }

  function end(focusButton: boolean) {
    open.current = false;
    refocus.current = focusButton;
    setRefusal("");
    setEditing(false);
  }

  async function commit() {
    if (saving.current) return;
    const value = draft.trim();
    if (!value && !allowEmpty) {
      setRefusal(strings.nameEmpty);
      return;
    }
    saving.current = true;
    let said: string | null = strings.nameNotSaved; // a save that throws is not saved
    try {
      const refused = await save(value);
      said = refused === null ? null : (refusalText(refused) ?? strings.nameNotSaved);
    } catch {
      // said below
    } finally {
      saving.current = false;
    }
    if (!open.current) return;
    if (said === null) end(true);
    else setRefusal(said);
  }

  // Spread onto the input; each caller adds its label, length and look.
  const input = {
    autoFocus: true,
    value: draft,
    "aria-invalid": refusal ? true : undefined,
    "aria-describedby": refusal ? refusalId : undefined,
    onChange: (event: ChangeEvent<HTMLInputElement>) => {
      setDraft(event.target.value);
      setRefusal("");
    },
    onKeyDown: (event: KeyboardEvent<HTMLInputElement>) => {
      if (event.key === "Enter") {
        event.preventDefault(); // no keypress: it would press the button the focus returns to
        void commit();
      }
      if (event.key === "Escape") end(true);
    },
    onBlur: () => {
      if (open.current) end(false);
    },
  };
  return { editing, refusal, refusalId, begin, button, input };
}
