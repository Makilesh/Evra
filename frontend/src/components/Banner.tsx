import { strings } from "@/strings";

interface BannerProps {
  message: string;
  hint?: string;
  action?: { label: string; onClick: () => void };
  onDismiss?: () => void;
}

// A calm notice: what happened, how to fix it, and at most one action.
export function Banner({ message, hint, action, onDismiss }: BannerProps) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-md border border-line bg-paper px-4 py-3 text-sm">
      <div className="flex-1">
        <p>{message}</p>
        {hint && <p className="mt-1 text-muted-ink">{hint}</p>}
      </div>
      {action && (
        <button type="button" onClick={action.onClick} className="rounded-md bg-accent px-3 py-1 text-paper">
          {action.label}
        </button>
      )}
      {onDismiss && (
        <button type="button" onClick={onDismiss} aria-label={strings.dismiss} className="px-1 text-muted-ink hover:text-ink">
          ×
        </button>
      )}
    </div>
  );
}
