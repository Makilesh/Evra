import { useEffect, useRef, useState } from "react";
import type { Utterance } from "@/bridge";
import { formatClock } from "@/format";
import { cn } from "@/lib/utils";
import { strings } from "@/strings";

interface TranscriptViewProps {
  utterances: Utterance[];
  follow: boolean;
  highlightId: string | null;
}

const NEAR_BOTTOM_PX = 40;

// Every line's time sits on the rule; a detent marks each change of speaker.
export function TranscriptView({ utterances, follow, highlightId }: TranscriptViewProps) {
  const box = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);
  // Lines that arrive while live land heavier and settle; an old meeting opens at rest.
  const [firstFresh] = useState(() => (follow ? utterances.length : Number.POSITIVE_INFINITY));

  useEffect(() => {
    const el = box.current;
    if (follow && el && atBottom.current) el.scrollTop = el.scrollHeight;
  }, [utterances.length, follow]);

  useEffect(() => {
    if (!highlightId || !box.current) return;
    const lines = Array.from(box.current.querySelectorAll<HTMLElement>("[data-utterance-id]"));
    lines.find((line) => line.dataset.utteranceId === highlightId)?.scrollIntoView?.({ block: "center" });
  }, [highlightId]);

  function onScroll() {
    const el = box.current;
    if (el) atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
  }

  if (utterances.length === 0 && !follow) {
    return <p className="px-[var(--gutter)] pt-8 text-muted">{strings.noTranscript}</p>;
  }
  return (
    <div
      ref={box}
      onScroll={onScroll}
      data-testid="transcript-scroll"
      className="h-full overflow-y-auto px-[var(--gutter)] pt-2 pb-12"
    >
      <ol aria-label={strings.transcriptTab} className="measure -mx-2.5">
        {utterances.map((u, index) => {
          const turn = index === 0 || utterances[index - 1].channel !== u.channel;
          return (
            <li
              key={u.id}
              data-utterance-id={u.id}
              data-highlighted={u.id === highlightId ? "true" : undefined}
              data-turn={turn ? "true" : undefined}
              data-fresh={index >= firstFresh ? "true" : undefined}
              className="line-row"
            >
              <span className="line-mid on-rule">
                {turn && <span aria-hidden="true" className="line-detent detent" />}
                <span className="line-time">{formatClock(u.start_ms)}</span>
              </span>
              <span className={turn ? cn("line-speaker caps", u.channel === 0 ? "text-you" : "text-them") : "sr-only"}>
                {u.speaker}
              </span>
              <p className="line-body">
                <span className="line-text">{u.text}</span>
              </p>
            </li>
          );
        })}
      </ol>
      {follow && (
        <div role="status" className="measure line-row listening -mx-2.5" data-turn={utterances.length === 0 ? undefined : "true"}>
          <span className="line-mid on-rule-fade">
            <span aria-hidden="true" className="listening-dot" />
          </span>
          <span className="line-speaker caps text-muted">{strings.listening}</span>
        </div>
      )}
    </div>
  );
}
