import { type CSSProperties, useCallback, useEffect, useRef, useState } from "react";
import { Banner } from "@/components/Banner";
import { MeetingList } from "@/components/MeetingList";
import { MeetingView } from "@/components/MeetingView";
import { Rail } from "@/components/Rail";
import { SettingsView } from "@/components/SettingsView";
import { padLines } from "@/notepad";
import { strings } from "@/strings";
import { useEvra } from "@/useEvra";

// The main window: the chipboard rail on the left, the open meeting (or Settings) on the pad.
export default function App() {
  const {
    state,
    people,
    setMeetingPerson,
    select,
    startRecording,
    stopRecording,
    writeNote,
    ask,
    prepareAsk,
    rename,
    setItemStatus,
    editNotes,
    dismissStartError,
    refreshMics,
    setTheme,
    setNoteModel,
    loadNoteModels,
    openDataFolder,
  } = useEvra();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsButton = useRef<HTMLButtonElement>(null);

  const closeSettings = useCallback(() => {
    setSettingsOpen(false);
    settingsButton.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === ",") {
        event.preventDefault();
        setSettingsOpen(true);
      } else if (event.key === "Escape" && settingsOpen) {
        closeSettings();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [settingsOpen, closeSettings]);

  if (state.bridgeError) {
    return (
      <main className="grid h-full place-items-center p-10">
        <div className="w-full max-w-xl">
          <Banner message={strings.bridgeDown} hint={state.bridgeError} />
        </div>
      </main>
    );
  }
  const { recording, detail } = state;
  const liveId = recording.state === "recording" ? (recording.meeting_id ?? null) : null;
  const isLive = detail !== null && detail.meeting.id === liveId;
  const canWrite = detail !== null && !isLive && recording.state === "idle" && detail.utterances.length > 0;
  const writingIds = Object.keys(state.noteStatus).filter((id) => state.noteStatus[id].stage);
  return (
    <div className="grid h-full grid-cols-[var(--rail-w)_minmax(0,1fr)]">
      <Rail
        appName={state.appName}
        recording={recording}
        levels={state.levels}
        mics={state.mics}
        startError={state.startError}
        onStart={(mic) => {
          setSettingsOpen(false);
          void startRecording(mic);
        }}
        onStop={() => void stopRecording()}
        onDismissError={dismissStartError}
        onRefreshMics={() => void refreshMics()}
        settingsOpen={settingsOpen}
        onOpenSettings={() => setSettingsOpen(true)}
        settingsButtonRef={settingsButton}
      >
        <MeetingList
          meetings={state.meetings}
          selectedId={settingsOpen ? null : state.selectedId}
          liveId={liveId}
          writingIds={writingIds}
          onSelect={(id) => {
            setSettingsOpen(false);
            select(id);
          }}
        />
      </Rail>
      <main className="min-h-0 min-w-0">
        {settingsOpen && state.settings ? (
          <SettingsView
            appName={state.appName}
            settings={state.settings}
            noteModels={state.noteModels}
            error={state.settingsError}
            onTheme={(theme) => void setTheme(theme)}
            onNoteModel={(model) => void setNoteModel(model)}
            onLoadModels={loadNoteModels}
            onOpenFolder={openDataFolder}
            onClose={closeSettings}
          />
        ) : detail ? (
          <MeetingView
            key={detail.meeting.id}
            detail={detail}
            isLive={isLive}
            noteStatus={state.noteStatus[detail.meeting.id]}
            hints={state.hints[detail.meeting.id]}
            canWrite={canWrite}
            notes={padLines(state.notes[detail.meeting.id], detail.notes)}
            notesFailed={state.notesSaveFailed[detail.meeting.id] === true}
            onWrite={() => void writeNote(detail.meeting.id)}
            onRename={(title) => rename(detail.meeting.id, title)}
            onAsk={(text) => ask(detail.meeting.id, text)}
            onPrepareAsk={() => prepareAsk(detail.meeting.id)}
            onItemStatus={(itemId, status) => void setItemStatus(itemId, status)}
            onNotes={(lines) => editNotes(detail.meeting.id, lines)}
            people={people}
            onSetPerson={(name) => setMeetingPerson(detail.meeting.id, name)}
          />
        ) : state.ready && state.meetings.length === 0 ? (
          <Welcome />
        ) : state.ready ? (
          <p className="px-[var(--gutter)] pt-[30px] text-muted">{strings.selectMeeting}</p>
        ) : null}
      </main>
    </div>
  );
}

// First run: what pressing Record will do, on the same rule the note uses.
function Welcome() {
  const shortcuts = [
    { keys: strings.searchShortcut, label: strings.searchShortcutHelp },
    { keys: strings.settingsShortcut, label: strings.settings },
  ];
  return (
    <div className="enter h-full overflow-y-auto px-[var(--gutter)] pt-[30px]">
      <h1 className="max-w-[18ch] font-display text-[clamp(2.25rem,4.6vw,3.75rem)] leading-[0.95] font-extrabold text-balance">
        {strings.welcomeTitle}
      </h1>
      <ol className="mt-8 max-w-[34rem]">
        {strings.welcomeSteps.map((step, index) => (
          <li key={step} className="welcome-step grid grid-cols-[2.5rem_minmax(0,1fr)]" style={{ "--i": index } as CSSProperties}>
            <span className="on-rule flex justify-center pt-[7px]">
              <span className="detent" />
            </span>
            <p className="pb-5 pl-2">{step}</p>
          </li>
        ))}
      </ol>
      <ul aria-label={strings.shortcuts} className="mt-6 flex flex-wrap gap-x-6 gap-y-2 pl-[3rem] text-[13px] leading-5 text-muted">
        {shortcuts.map((shortcut) => (
          <li key={shortcut.keys} className="flex items-center gap-2">
            <span className="kbd">{shortcut.keys}</span>
            {shortcut.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
