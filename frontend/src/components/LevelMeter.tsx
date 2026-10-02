interface LevelMeterProps {
  label: string;
  value: number;
}

// One channel's loudness (0..1) while recording, so the owner sees both sides are live.
export function LevelMeter({ label, value }: LevelMeterProps) {
  const level = Math.min(1, Math.max(0, value));
  return (
    <div className="flex items-center gap-1.5 text-xs text-muted-ink">
      <span aria-hidden="true">{label}</span>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={level}
        className="h-1.5 w-12 overflow-hidden rounded-full bg-line"
      >
        <div className="h-full bg-accent transition-[width] duration-100" style={{ width: `${Math.round(level * 100)}%` }} />
      </div>
    </div>
  );
}
