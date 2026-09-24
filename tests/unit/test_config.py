from pathlib import Path

from evra.config import Settings, debug_enabled, load_settings, save_settings


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    s = load_settings(tmp_path / "settings.toml")
    assert s == Settings()
    assert s.default_mode == "one_on_one"
    assert s.audio_retention == "30d"
    assert s.live_transcript is True
    assert s.llm.provider == "ollama"


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "cfg" / "settings.toml"
    s = Settings(default_mode="meeting", audio_retention="forever", theme="dark")
    save_settings(path, s)
    assert load_settings(path) == s


def test_invalid_toml_resets_to_defaults_and_keeps_backup(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_text("this is = = not toml", encoding="utf-8")
    assert load_settings(path) == Settings()
    assert not path.exists()
    assert (tmp_path / "settings.toml.bad").read_text(encoding="utf-8") == "this is = = not toml"


def test_invalid_value_resets_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_text('default_mode = "party"\n', encoding="utf-8")
    assert load_settings(path) == Settings()
    assert (tmp_path / "settings.toml.bad").exists()


def test_unknown_keys_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_text('future_option = 3\ntheme = "light"\n', encoding="utf-8")
    assert load_settings(path).theme == "light"


def test_debug_enabled_reads_only_evra_debug() -> None:
    assert debug_enabled({"EVRA_DEBUG": "1"}) is True
    assert debug_enabled({"EVRA_DEBUG": "0"}) is False
    assert debug_enabled({}) is False
