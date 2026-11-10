# Settings, first set — Plan

**Goal:** a clean Settings page with only the settings Evra needs now, and a light window by default with Dark as a choice.

**Spec:** the owner's request (2026-11-10), the research report in `private/research/reports/`, and DECISIONS "Theme: light by default, Dark in Settings" and "Settings, first set".

**Architecture:**
- The settings file stays the single source (`config.Settings`, TOML).
- `MeetingService` changes one value at a time: it reads the file again under a lock and saves only non-defaults.
- `BridgeApi` adds `get_settings`, `set_theme`, `set_note_model`, `list_note_models` and `open_data_folder`.
- React shows Settings as a page on the pad. The theme reaches the first paint through the URL fragment.

## Global Constraints
- At most four or five settings; changes apply at once; an unavailable setting is disabled with its reason.
- No setting before its feature exists; the microphone stays in the rail.
- Light is the default. Dark and Match Windows are saved as `theme = "dark"` / `"system"`, and an unknown value reads as light without a reset.
- Evra opens no listener: Open folder starts Explorer, and model names are checked against a strict pattern.

## Tasks
- [x] Settings: light default, a lenient theme validator, and changing one value while keeping file edits (tests: config, service).
- [x] Bridge calls, with the model-name check and the folder opener (tests: bridge surface, refusals).
- [x] The window opens in the saved theme: the pad background plus `#theme=dark`, checked against .NET's `Uri` (tests: window, app).
- [x] Frontend: theme from the fragment, the Settings page, the rail entry, `Ctrl ,` / Esc, saving and failure states (tests: SettingsView, Rail, App, theme).
- [x] Edge check with the fake bridge; real-window check at 150% (dark restart, real Ollama models, Open folder).
- [x] DECISIONS, PRODUCT, BUILD, DESIGN + sidecar, PROGRESS, BACKLOG.
