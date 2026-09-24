import { useEffect, useState } from "react";
import { getApi, onEvent, type AppInfo } from "@/bridge";

// M0 bootstrap screen: proves both bridge directions. Replaced by the real UI from M3.
export default function App() {
  const [info, setInfo] = useState<AppInfo | null>(null);
  const [reply, setReply] = useState("");
  const [lastEvent, setLastEvent] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const off = onEvent("app.hello", (payload) => setLastEvent(JSON.stringify(payload)));
    getApi()
      .then(async (api) => {
        setInfo(await api.app_info());
        await api.request_hello();
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
    return off;
  }, []);

  async function handlePing() {
    try {
      const api = await getApi();
      setReply((await api.ping("hello")).reply);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <main className="mx-auto max-w-xl p-10">
      <h1 className="font-serif text-3xl">{info ? `${info.name} ${info.version}` : "Evra"}</h1>
      <p className="mt-2 text-muted-ink">Bootstrap check: the window talks to Python.</p>
      <button
        type="button"
        onClick={handlePing}
        className="mt-6 rounded-md bg-accent px-4 py-2 text-paper"
      >
        Ping Python
      </button>
      {reply && (
        <p role="status" className="mt-4">
          {reply}
        </p>
      )}
      {lastEvent && (
        <p data-testid="last-event" className="mt-2 text-sm text-muted-ink">
          {lastEvent}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-4 text-rec">
          {error}
        </p>
      )}
    </main>
  );
}
