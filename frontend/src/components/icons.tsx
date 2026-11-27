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

// A check-list: a ticked line over one still open, for the promises kept and still to keep.
export function PromisesIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M2.25 4.5l1.5 1.5 2.75-3" />
      <path d="M9 4.75h4.75" />
      <rect x="2.5" y="9.25" width="3.5" height="3.5" rx="0.75" />
      <path d="M9 11h4.75" />
    </Icon>
  );
}

// Two people, one a step behind the other: the people you have 1:1s with.
export function PeopleIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="6" cy="5.25" r="2.25" />
      <path d="M2.25 13c0-2.2 1.6-3.75 3.75-3.75s3.75 1.55 3.75 3.75" />
      <path d="M10.25 3.15a2.25 2.25 0 0 1 0 4.2" />
      <path d="M11.75 9.6c1.25.45 2 1.6 2 3.4" />
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
