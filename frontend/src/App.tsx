import { Banner } from "@/components/Banner";
import { MeetingList } from "@/components/MeetingList";
import { MeetingView } from "@/components/MeetingView";
import { TopBar } from "@/components/TopBar";
import { strings } from "@/strings";
import { useEvra } from "@/useEvra";

// The main window (M3c spec §4): top bar, meetings list, the open meeting.
export default function App() {
  const { state, select, startRecording, stopRecording, writeNote, rename, dismissStartError } = useEvra();
  if (state.bridgeError) {
    return (
      <main className="mx-auto max-w-xl p-10">
        <Banner message={strings.bridgeDown} hint={state.bridgeError} />
      </main>
    );
  }
  const { recording, detail } = state;
  const liveId = recording.state === "recording" ? (recording.meeting_id ?? null) : null;
  const isLive = detail !== null && detail.meeting.id === liveId;
  const canWrite = detail !== null && !isLive && recording.state === "idle" && detail.utterances.length > 0;
  return (
    <div className="flex h-screen flex-col">
      <TopBar
        appName={state.appName}
        recording={recording}
        levels={state.levels}
        mics={state.mics}
        startError={state.startError}
        onStart={(mic) => void startRecording(mic)}
        onStop={() => void stopRecording()}
        onDismissError={dismissStartError}
      />
      <div className="flex min-h-0 flex-1">
        <aside className="w-72 shrink-0 border-r border-line">
          <MeetingList meetings={state.meetings} selectedId={state.selectedId} liveId={liveId} onSelect={select} />
        </aside>
        <main className="min-w-0 flex-1">
          {detail ? (
            <MeetingView
              key={detail.meeting.id}
              detail={detail}
              isLive={isLive}
              noteStatus={state.noteStatus[detail.meeting.id]}
              hints={state.hints[detail.meeting.id]}
              canWrite={canWrite}
              onWrite={() => void writeNote(detail.meeting.id)}
              onRename={(title) => rename(detail.meeting.id, title)}
            />
          ) : (
            <p className="p-10 text-muted-ink">{strings.selectMeeting}</p>
          )}
        </main>
      </div>
    </div>
  );
}
