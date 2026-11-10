import { useEffect, useId, useState, type ReactNode } from "react";
import type { Levels, MicList, RecordingPhase, RecordingState } from "@/bridge";
import { Banner } from "@/components/Banner";
import { ChevronIcon } from "@/components/icons";
import { LevelMeter } from "@/components/LevelMeter";
import { formatClock } from "@/format";
import { strings } from "@/strings";
import type { StartError } from "@/useEvra";

interface RailProps {
  appName: string;
  recording: RecordingState;
  levels: Levels;
  mics: MicList | null;
  startError: StartError | null;
  onStart: (mic: string) => void;
  onStop: () => void;
  onDismissError: () => void;
  onRefreshMics: () => void;
  now?: () => number;
  /** The meetings list, placed between the record block and the microphone. */
  children?: ReactNode;
}

function useElapsed(startedAt: number | null, now: () => number): number {
  const [, tick] = useState(0);
  useEffect(() => {
    if (startedAt === null) return;
    const timer = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);
  return startedAt === null ? 0 : now() - startedAt;
}

const BUSY: Record<Exclude<RecordingPhase, "idle" | "recording">, string> = {
  loading: strings.loading,
  stopping: strings.stopping,
  processing: strings.writingNote,
};

// The chipboard rail: the wordmark, the record block, the meetings, the microphone.
export function Rail({
  appName,
  recording,
  levels,
  mics,
  startError,
  onStart,
  onStop,
  onDismissError,
  onRefreshMics,
  now = Date.now,
  children,
}: RailProps) {
  const [picked, setPicked] = useState<string | null>(null);
  const micId = useId();
  const phase = recording.state;
  const chosen = picked ?? mics?.chosen ?? "";
  const known = mics?.mics ?? [];
  const elapsed = useElapsed(phase === "recording" ? (recording.started_at ?? null) : null, now);

  return (
    <aside className="flex h-full min-h-0 flex-col bg-chip shadow-[inset_-1px_0_0_var(--chip-edge)]">
      <div className="px-[18px] pt-[22px]">
        <p className="font-display text-[30px] leading-none font-extrabold">{appName}</p>
        <p className="mt-1.5 text-[12.5px] leading-[18px] text-chip-ink">{strings.claim}</p>
      </div>

      <div className="px-[18px] pt-5">
        {phase === "recording" ? (
          <div className="rounded-[11px] bg-rec-fill p-3 text-on-rec">
            <div className="flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <p className="caps flex items-center gap-1.5 text-[13px] leading-4">
                  <span aria-hidden="true" className="size-2 rounded-full bg-on-rec" />
                  {strings.liveNow}
                </p>
                <p
                  role="timer"
                  aria-label={strings.recordingTime}
                  className="font-display text-[28px] leading-8 font-bold tabular-nums"
                >
                  {formatClock(elapsed)}
                </p>
              </div>
              <button
                type="button"
                onClick={onStop}
                className="h-9 shrink-0 rounded-lg bg-on-rec px-4 font-semibold text-rec-fill hover:bg-on-rec/90"
              >
                {strings.stop}
              </button>
            </div>
            <div className="mt-3 grid gap-2">
              <LevelMeter label={strings.you} value={levels.you} />
              <LevelMeter label={strings.them} value={levels.them} />
            </div>
          </div>
        ) : phase === "idle" ? (
          <button
            type="button"
            onClick={() => onStart(chosen)}
            className="flex h-12 w-full items-center gap-3 rounded-[11px] bg-ink px-4 text-[16px] font-semibold text-pad transition-colors hover:bg-ink/88"
          >
            <span aria-hidden="true" className="size-3 rounded-full bg-rec" />
            {strings.record}
          </button>
        ) : (
          <button
            type="button"
            disabled
            className={
              "flex h-12 w-full items-center gap-3 rounded-[11px] px-4 text-[16px] font-semibold text-pad " +
              (phase === "processing" ? "bg-rule" : "bg-ink")
            }
          >
            {BUSY[phase]}
          </button>
        )}
      </div>

      {startError && (
        <div className="px-[18px] pt-2.5">
          <Banner message={startError.error} hint={startError.hint} onDismiss={onDismissError} />
        </div>
      )}

      {children}

      <div className="px-[18px] pt-3 pb-4 shadow-[inset_0_1px_0_var(--chip-edge)]">
        <label htmlFor={micId} className="caps block text-[13px] leading-4 text-chip-ink">
          {strings.microphone}
        </label>
        <div className="relative mt-1.5">
          <select
            id={micId}
            value={chosen}
            disabled={phase !== "idle"}
            onChange={(event) => setPicked(event.target.value)}
            onFocus={onRefreshMics}
            className="h-10 w-full appearance-none truncate rounded-[10px] bg-chip-well pr-8 pl-3 text-[14px] text-ink disabled:text-chip-ink"
          >
            <option value="">{strings.windowsDefault(mics?.default ?? "")}</option>
            {chosen !== "" && !known.includes(chosen) && <option value={chosen}>{strings.notConnected(chosen)}</option>}
            {known.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <ChevronIcon className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-chip-ink" />
        </div>
      </div>
    </aside>
  );
}
