import { type RefObject, useEffect } from "react";

/** A page that opens with nothing focused takes the focus on its title, so the keyboard lands on
 *  it: the control that opened it went with the page before (a person's row, Forget). Opened
 *  from a control that stays (a rail link), the focus stays there. */
export function useFocusOnLanding(title: RefObject<HTMLElement | null>): void {
  useEffect(() => {
    const active = document.activeElement;
    if (!active || active === document.body) title.current?.focus();
  }, [title]);
}
