import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import type { NoteModels, SettingsInfo, Theme } from "@/bridge";
import { Banner } from "@/components/Banner";
import { CheckIcon, ChevronIcon, CloseIcon } from "@/components/icons";
import { strings } from "@/strings";

interface SettingsViewProps {
  appName: string;
  settings: SettingsInfo;
  /** null while Ollama is being asked. */
  noteModels: NoteModels | null;
  error: string;
  onTheme: (theme: Theme) => void;
  onNoteModel: (model: string) => void;
  /** Must be stable: it runs once each time the page opens. */
  onLoadModels: () => void;
  onOpenFolder: () => Promise<boolean>;
  onClose: () => void;
}

const THEMES: Theme[] = ["light", "dark"];

// Settings: a short page on the same timed rule as the note, one detent per setting.
// Every change applies at once; there is no Save button.
export function SettingsView({
  appName,
  settings,
  noteModels,
  error,
  onTheme,
  onNoteModel,
  onLoadModels,
  onOpenFolder,
  onClose,
}: SettingsViewProps) {
  const heading = useRef<HTMLHeadingElement>(null);
  const ids = useId();
  useEffect(() => heading.current?.focus(), []);
  useEffect(() => {
    onLoadModels();
  }, [onLoadModels]);

  return (
    <div className="h-full overflow-y-auto">
      <div className="px-[var(--gutter)] pt-[30px] pb-10">
        <header className="flex items-start justify-between gap-6">
          <h1
            ref={heading}
            tabIndex={-1}
            className="font-display text-[clamp(2.25rem,4.6vw,3.75rem)] leading-[0.95] font-extrabold outline-none"
          >
            {strings.settings}
          </h1>
          <button
            type="button"
            aria-label={strings.closeSettings}
            title={strings.closeHint}
            onClick={onClose}
            className="mt-[0.15em] inline-flex size-8 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-band hover:text-ink"
          >
            <CloseIcon />
          </button>
        </header>

        {error && (
          <div className="mt-5 max-w-[42rem]">
            <Banner message={error} />
          </div>
        )}

        <ol className="mt-8 max-w-[42rem]">
          <Row id={`${ids}-theme`} title={strings.theme}>
            <ThemePicker labelledBy={`${ids}-theme`} theme={settings.theme} onTheme={onTheme} />
          </Row>
          <Row id={`${ids}-model`} title={strings.noteModel} help={strings.noteModelHelp}>
            <ModelPicker
              labelledBy={`${ids}-model`}
              current={settings.note_model}
              recommended={settings.default_note_model}
              noteModels={noteModels}
              onNoteModel={onNoteModel}
              onCheckAgain={onLoadModels}
            />
          </Row>
          <Row id={`${ids}-folder`} title={strings.meetingsFolder} help={strings.meetingsFolderHelp}>
            <Folder path={settings.data_dir} onOpenFolder={onOpenFolder} />
          </Row>
          <Row id={`${ids}-about`} title={strings.about} help={strings.aboutHelp} last>
            <p>{strings.appVersion(appName, settings.version)}</p>
          </Row>
        </ol>
      </div>
    </div>
  );
}

function Row({
  id,
  title,
  help,
  last = false,
  children,
}: {
  id: string;
  title: string;
  help?: string;
  last?: boolean;
  children: ReactNode;
}) {
  return (
    <li className="grid grid-cols-[2.5rem_minmax(0,1fr)]">
      <span className={"flex justify-center pt-[4px]" + (last ? "" : " on-rule")}>
        <span className="detent" />
      </span>
      <section aria-labelledby={id} className={"min-w-0 pl-2" + (last ? "" : " pb-9")}>
        <h2 id={id} className="caps text-[15px] leading-[18px] text-rule">
          {title}
        </h2>
        {help && <p className="mt-1 max-w-[36rem] text-[13px] leading-5 text-muted">{help}</p>}
        <div className="mt-3">{children}</div>
      </section>
    </li>
  );
}

function ThemePicker({ labelledBy, theme, onTheme }: { labelledBy: string; theme: Theme; onTheme: (t: Theme) => void }) {
  const name = useId();
  return (
    <div role="radiogroup" aria-labelledby={labelledBy} className="-m-2 flex flex-wrap gap-2">
      {THEMES.map((option) => {
        const chosen = option === theme;
        // The chosen option fills band-deep (state is a filled area, never an outline).
        return (
          <label
            key={option}
            className={
              "cursor-pointer rounded-[14px] p-2 pb-2.5 transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-rule " +
              (chosen ? "bg-band-deep" : "hover:bg-band")
            }
          >
            <input
              type="radio"
              name={name}
              value={option}
              checked={chosen}
              onChange={() => onTheme(option)}
              className="sr-only"
            />
            <ThemePreview theme={option} />
            <span className="mt-2 flex items-center gap-1.5 px-0.5 font-semibold">
              {chosen ? <CheckIcon /> : <span aria-hidden="true" className="size-4" />}
              {strings.themeNames[option]}
            </span>
          </label>
        );
      })}
    </div>
  );
}

// The window in miniature, drawn in that theme's own tokens: the chipboard rail with Record,
// then the pad with a title, the timed rule and a point on a band.
function ThemePreview({ theme }: { theme: Theme }) {
  return (
    <span
      aria-hidden="true"
      className={`${theme} flex h-[78px] w-[138px] overflow-hidden rounded-[9px] border border-ink/15 bg-pad`}
    >
      <span className="flex w-[36px] shrink-0 flex-col gap-[5px] bg-chip px-[6px] pt-[7px]">
        <span className="h-[5px] w-[15px] rounded-[2px] bg-ink" />
        <span className="flex h-[11px] items-center rounded-[3px] bg-ink pl-[3px]">
          <span className="size-[5px] rounded-full bg-rec" />
        </span>
        <span className="h-[3px] w-[20px] rounded-[2px] bg-chip-ink/60" />
        <span className="h-[3px] w-[15px] rounded-[2px] bg-chip-ink/60" />
      </span>
      <span className="relative min-w-0 flex-1">
        <span className="absolute top-[8px] left-[8px] h-[7px] w-[52px] rounded-[2px] bg-ink" />
        <span className="absolute inset-x-[4px] top-[42px] h-[13px] rounded-[3px] bg-band" />
        <span className="absolute top-[24px] bottom-0 left-[54px] w-[2px] bg-rule" />
        <span className="absolute top-[27px] left-[52px] size-[6px] bg-rule" />
        <span className="absolute top-[37px] left-[8px] h-[3px] w-[36px] rounded-[2px] bg-ink/85" />
        <span className="absolute top-[47px] left-[8px] h-[3px] w-[30px] rounded-[2px] bg-ink/85" />
        <span className="absolute top-[37px] left-[64px] h-[3px] w-[28px] rounded-[2px] bg-muted/70" />
        <span className="absolute top-[47px] left-[64px] h-[3px] w-[22px] rounded-[2px] bg-muted/70" />
      </span>
    </span>
  );
}

function ModelPicker({
  labelledBy,
  current,
  recommended,
  noteModels,
  onNoteModel,
  onCheckAgain,
}: {
  labelledBy: string;
  current: string;
  recommended: string;
  noteModels: NoteModels | null;
  onNoteModel: (model: string) => void;
  onCheckAgain: () => void;
}) {
  const listed = noteModels?.ok ? noteModels.models : [];
  const options = listed.includes(current) ? listed : [current, ...listed];
  return (
    <>
      <div className="relative max-w-[22rem]">
        <select
          aria-labelledby={labelledBy}
          value={current}
          disabled={listed.length === 0}
          onChange={(event) => onNoteModel(event.target.value)}
          className="h-10 w-full appearance-none truncate rounded-[10px] bg-band pr-9 pl-3 text-ink disabled:cursor-not-allowed disabled:bg-band/50 disabled:text-muted"
        >
          {options.map((model) => (
            <option key={model} value={model}>
              {model === recommended ? strings.recommended(model) : model}
            </option>
          ))}
        </select>
        <ChevronIcon className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-muted" />
      </div>
      {noteModels === null ? (
        <p className="mt-2 text-[13px] leading-5 text-muted">{strings.findingModels}</p>
      ) : !noteModels.ok ? (
        <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] leading-5 text-muted">
          {strings.ollamaQuiet}
          <button
            type="button"
            onClick={onCheckAgain}
            className="rounded-md font-semibold text-ink underline decoration-rule underline-offset-[3px] hover:decoration-2"
          >
            {strings.checkAgain}
          </button>
        </p>
      ) : (
        !listed.includes(current) && (
          <p className="mt-2 text-[13px] leading-5 text-muted">
            {strings.modelMissing(current)} <span className="whitespace-nowrap">{strings.pullCommand(current)}</span>
          </p>
        )
      )}
    </>
  );
}

function Folder({ path, onOpenFolder }: { path: string; onOpenFolder: () => Promise<boolean> }) {
  const [failed, setFailed] = useState(false);
  return (
    <>
      <p className="[overflow-wrap:anywhere]">{path}</p>
      <button
        type="button"
        onClick={async () => setFailed(!(await onOpenFolder()))}
        className="mt-3 inline-flex h-9 items-center rounded-lg bg-band px-3 text-[13px] leading-5 font-semibold transition-colors hover:bg-band-deep"
      >
        {strings.openFolder}
      </button>
      {failed && (
        <p role="alert" className="mt-2 text-[13px] leading-5 text-muted">
          {strings.folderNotOpened}
        </p>
      )}
    </>
  );
}
