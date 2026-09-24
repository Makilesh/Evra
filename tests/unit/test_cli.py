import pytest

import evra
from evra import constants
from evra.__main__ import main


def test_version_flag_prints_name_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"Evra {evra.__version__}"


def test_version_comes_from_package_metadata() -> None:
    assert evra.__version__ == "0.1.0"


def test_names_live_in_constants() -> None:
    assert constants.APP_NAME == "Evra"
    assert constants.APP_ID == "evra"
    assert constants.WAKE_PHRASE == "Hey Evra"


def test_no_command_prints_help_and_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "usage:" in capsys.readouterr().out
