import { CloseIcon } from "@/components/icons";
import { strings } from "@/strings";

interface BannerProps {
  message: string;
  hint?: string;
  action?: { label: string; onClick: () => void };
  onDismiss?: () => void;
}

// A calm notice that fills its row in the pad's state green (red is kept for recording):
// what happened, how to fix it, and at most one action.
export function Banner({ message, hint, action, onDismiss }: BannerProps) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-[10px] bg-band-deep px-4 py-3">
      <div className="min-w-0 flex-1">
        <p className="font-semibold">{message}</p>
        {hint && <p className="mt-1 text-ink/80">{hint}</p>}
      </div>
      {action && (
        <button
          type="button"
          onClick={action.onClick}
          className="shrink-0 rounded-lg bg-ink px-3 py-1 font-semibold text-pad hover:bg-ink/88"
        >
          {action.label}
        </button>
      )}
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label={strings.dismiss}
          className="-m-1 shrink-0 rounded-md p-1 text-ink/80 hover:text-ink"
        >
          <CloseIcon />
        </button>
      )}
    </div>
  );
}
