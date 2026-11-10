interface LevelMeterProps {
  label: string;
  value: number;
}

// One channel's loudness (0..1) while recording, so the owner sees both sides are live.
// It sits on the red recording block; the fill moves with transform, never width.
export function LevelMeter({ label, value }: LevelMeterProps) {
  const level = Math.min(1, Math.max(0, value));
  return (
    <div className="flex items-center gap-2">
      <span aria-hidden="true" className="caps w-10 text-[12px] leading-none">
        {label}
      </span>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={level}
        className="h-1.5 flex-1 overflow-hidden rounded-full bg-on-rec/25"
      >
        <div className="meter-fill h-full bg-on-rec" style={{ transform: `scaleX(${level})` }} />
      </div>
    </div>
  );
}
