import { useEffect, useState } from "react";
import type { Levels, MicList, RecordingPhase, RecordingState } from "@/bridge";
import { Banner } from "@/components/Banner";
import { LevelMeter } from "@/components/LevelMeter";
import { formatClock } from "@/format";
import { cn } from "@/lib/utils";
import { strings } from "@/strings";
import type { StartError } from "@/useEvra";

interface TopBarProps {
  appName: string;
  recording: RecordingState;
  levels: Levels;
  mics: MicList | null;
  startError: StartError | null;
  onStart: (mic: string) => void;
  onStop: () => void;
  onDismissError: () => void;
  now?: () => number;
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

export function TopBar({ appName, recording, levels, mics, startError, onStart, onStop, onDismissError, now = Date.now }: TopBarProps) {
  const [picked, setPicked] = useState<string | null>(null);
  const phase = recording.state;
  const chosen = picked ?? mics?.chosen ?? "";
  const known = mics?.mics ?? [];
  const elapsed = useElapsed(phase === "recording" ? (recording.started_at ?? null) : null, now);
  return (
    <header className="border-b border-line">
      <div className="flex items-center gap-3 px-4 py-2">
        <span className="font-serif text-lg">{appName}</span>
        <div className="ml-auto flex items-center gap-3">
          {phase === "recording" && (
            <>
              <LevelMeter label={strings.you} value={levels.you} />
              <LevelMeter label={strings.them} value={levels.them} />
              <span aria-label={strings.recordingTime} className="tabular-nums text-sm text-rec">
                {formatClock(elapsed)}
              </span>
            </>
          )}
          <select
            aria-label={strings.microphone}
            value={chosen}
            disabled={phase !== "idle"}
            onChange={(event) => setPicked(event.target.value)}
            className="max-w-64 rounded-md border border-line bg-paper px-2 py-1 text-sm disabled:opacity-60"
          >
            <option value="">{strings.windowsDefault(mics?.default ?? "")}</option>
            {chosen !== "" && !known.includes(chosen) && <option value={chosen}>{strings.notConnected(chosen)}</option>}
            {known.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          {phase === "recording" ? (
            <button type="button" onClick={onStop} className="rounded-md bg-rec px-4 py-1.5 text-sm text-paper">
              {strings.stop}
            </button>
          ) : phase === "idle" ? (
            <button type="button" onClick={() => onStart(chosen)} className="rounded-md bg-accent px-4 py-1.5 text-sm text-paper">
              <span aria-hidden="true">● </span>
              {strings.record}
            </button>
          ) : (
            <button type="button" disabled className={cn("rounded-md bg-accent px-4 py-1.5 text-sm text-paper opacity-60")}>
              {BUSY[phase]}
            </button>
          )}
        </div>
      </div>
      {startError && (
        <div className="px-4 pb-2">
          <Banner message={startError.error} hint={startError.hint} onDismiss={onDismissError} />
        </div>
      )}
    </header>
  );
}
