import { type CSSProperties, useCallback, useEffect, useRef, useState } from "react";
import { Banner } from "@/components/Banner";
import { MeetingList } from "@/components/MeetingList";
import { MeetingView } from "@/components/MeetingView";
import { PromisesView } from "@/components/PromisesView";
import { Rail, type Page } from "@/components/Rail";
import { SettingsView } from "@/components/SettingsView";
import { padLines } from "@/notepad";
import { strings } from "@/strings";
import { useEvra } from "@/useEvra";

/** The meeting a promise opened: on its note, or on its transcript at the line it came from. */
interface Opened {
  meetingId: string;
  utteranceId: string | null;
}

// The main window: the chipboard rail on the left; on the pad, the open meeting, the Promises
// page or Settings.
export default function App() {
  const {
    state,
    people,
    setMeetingPerson,
    promises,
    openPromises,
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
  const [page, setPage] = useState<Page>("meeting");
  const [opened, setOpened] = useState<Opened | null>(null);
  const settingsButton = useRef<HTMLButtonElement>(null);
  const beforeSettings = useRef<Page>("meeting"); // the page closing Settings goes back to

  const openPage = useCallback(
    (next: Page) => {
      if (next === "settings" && page !== "settings") beforeSettings.current = page;
      setOpened(null); // a meeting opened from a promise opens as usual the next time
      setPage(next);
    },
    [page],
  );

  const closeSettings = useCallback(() => {
    setPage(beforeSettings.current);
    settingsButton.current?.focus();
  }, []);

  // A promise's meeting, on its note, or on its transcript at the line the promise came from.
  const openMeeting = useCallback(
    (meetingId: string, utteranceId?: string) => {
      openPage("meeting");
      setOpened({ meetingId, utteranceId: utteranceId ?? null });
      select(meetingId);
    },
    [openPage, select],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === ",") {
        event.preventDefault();
        openPage("settings");
      } else if (event.key === "Escape" && page === "settings") {
        closeSettings();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [page, openPage, closeSettings]);

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
          openPage("meeting");
          void startRecording(mic);
        }}
        onStop={() => void stopRecording()}
        onDismissError={dismissStartError}
        onRefreshMics={() => void refreshMics()}
        page={page}
        onOpenPage={openPage}
        promiseCount={openPromises}
        settingsButtonRef={settingsButton}
      >
        <MeetingList
          meetings={state.meetings}
          selectedId={page === "meeting" ? state.selectedId : null}
          liveId={liveId}
          writingIds={writingIds}
          onSelect={(id) => {
            openPage("meeting");
            select(id);
          }}
        />
      </Rail>
      <main className="min-h-0 min-w-0">
        {page === "promises" ? (
          <PromisesView
            promises={promises}
            onStatus={(itemId, status) => void setItemStatus(itemId, status)}
            onOpenMeeting={openMeeting}
          />
        ) : page === "settings" && state.settings ? (
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
            openAt={opened?.meetingId === detail.meeting.id ? opened.utteranceId : null}
            focusTab={opened?.meetingId === detail.meeting.id}
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
