import { strings } from "@/strings";

interface StampProps {
  model: string;
  points: number;
}

// Provenance as one mark: where the note was written, by which model, how many points were checked.
export function Stamp({ model, points }: StampProps) {
  return (
    <div className="stamp shrink-0">
      <p className="caps text-[15px] leading-4">{strings.writtenHere}</p>
      <p className="text-[12.5px] leading-4 font-medium">{model}</p>
      <p className="text-[12.5px] leading-4 font-medium">{strings.pointsChecked(points)}</p>
    </div>
  );
}
