import tomllib
from pathlib import Path

from evra.config import LlmSettings, Settings, debug_enabled, load_settings, save_settings


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


def test_the_window_is_light_by_default() -> None:
    assert Settings().theme == "light"


def test_an_unknown_theme_becomes_light_and_keeps_the_rest(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_text('theme = "sepia"\nmic_name = "Headset"\n', encoding="utf-8")
    s = load_settings(path)
    assert (s.theme, s.mic_name) == ("light", "Headset")
    assert not (tmp_path / "settings.toml.bad").exists()


def test_match_windows_is_a_theme_choice(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    save_settings(path, Settings(theme="system"))
    assert load_settings(path).theme == "system"


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


def test_utf8_bom_file_is_read_not_reset(tmp_path: Path) -> None:
    # PowerShell 5 `Set-Content -Encoding UTF8` and some editors write a BOM.
    path = tmp_path / "settings.toml"
    path.write_bytes(b"\xef\xbb\xbf" + b'theme = "dark"\n')
    assert load_settings(path).theme == "dark"
    assert path.exists()
    assert not (tmp_path / "settings.toml.bad").exists()


def test_the_microphone_defaults_to_windows_default_and_round_trips(tmp_path: Path) -> None:
    assert Settings().mic_name == ""
    path = tmp_path / "settings.toml"
    save_settings(path, Settings(mic_name="Headset (realme Buds Air7)"))
    assert load_settings(path).mic_name == "Headset (realme Buds Air7)"


def test_only_changed_values_are_saved_so_new_defaults_still_apply(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    save_settings(path, Settings(mic_name="Headset (Buds)"))
    assert tomllib.loads(path.read_text(encoding="utf-8")) == {"mic_name": "Headset (Buds)"}
    assert load_settings(path) == Settings(mic_name="Headset (Buds)")
    save_settings(path, Settings(llm=LlmSettings(model="qwen3.5:9b")))
    assert tomllib.loads(path.read_text(encoding="utf-8")) == {"llm": {"model": "qwen3.5:9b"}}
