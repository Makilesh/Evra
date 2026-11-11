// Authored icons: 16px, one 1.5px stroke, drawn in the text colour.
import type { ReactNode, SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function Icon({ children, ...props }: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 16 16"
      width={16}
      height={16}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {children}
    </svg>
  );
}

export function PencilIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M10.5 2.5l3 3L6 13H3v-3z" />
      <path d="M9 4l3 3" />
    </Icon>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 4l8 8M12 4l-8 8" />
    </Icon>
  );
}

export function CopyIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="5.5" y="5.5" width="8" height="8" rx="1.5" />
      <path d="M10.5 5.5v-2a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2" />
    </Icon>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3 8.5l3 3 7-7" />
    </Icon>
  );
}

export function ChevronIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 6l4 4 4-4" />
    </Icon>
  );
}

// Two sliders: settings as adjustments, drawn in the same 1.5px stroke as the other icons.
export function SettingsIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M2.5 5h5.75M11.75 5h1.75M2.5 11h1.75M7.75 11h5.75" />
      <circle cx="10" cy="5" r="1.75" />
      <circle cx="6" cy="11" r="1.75" />
    </Icon>
  );
}

export function SearchIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="7" cy="7" r="4.25" />
      <path d="M10.25 10.25L13.5 13.5" />
    </Icon>
  );
}
