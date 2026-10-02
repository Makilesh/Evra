import { useEffect, useRef } from "react";
import type { Utterance } from "@/bridge";
import { formatClock } from "@/format";
import { cn } from "@/lib/utils";
import { strings } from "@/strings";

interface TranscriptViewProps {
  utterances: Utterance[];
  follow: boolean;
  highlightId: string | null;
}

const SPEAKER_COLOUR: Record<number, string> = {
  0: "text-accent",
  1: "text-amber-700 dark:text-amber-400",
};
const NEAR_BOTTOM_PX = 40;

export function TranscriptView({ utterances, follow, highlightId }: TranscriptViewProps) {
  const box = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);

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

  if (utterances.length === 0) return <p className="p-6 text-muted-ink">{strings.noTranscript}</p>;
  return (
    <div ref={box} onScroll={onScroll} data-testid="transcript-scroll" className="h-full overflow-y-auto px-6 py-4">
      <ol aria-label={strings.transcriptTab} className="space-y-1">
        {utterances.map((u) => (
          <li
            key={u.id}
            data-utterance-id={u.id}
            data-highlighted={u.id === highlightId ? "true" : undefined}
            className={cn("flex gap-3 rounded-md px-2 py-1", u.id === highlightId && "bg-accent/15")}
          >
            <span className="shrink-0 pt-1 text-xs tabular-nums text-muted-ink">{formatClock(u.start_ms)}</span>
            <span className={cn("shrink-0 pt-0.5 text-sm font-semibold", SPEAKER_COLOUR[u.channel] ?? "text-muted-ink")}>
              {u.speaker}
            </span>
            <span className="font-serif leading-relaxed">{u.text}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
