from pathlib import Path

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


def test_run_subcommand_is_registered() -> None:
    from evra.__main__ import build_parser

    args = build_parser().parse_args(["run", "--dev", "--debug", "--data-dir", "D:/x y"])
    assert args.command == "run" and args.dev is True and args.debug is True
    assert str(args.data_dir) == str(Path("D:/x y"))


def test_run_without_data_dir_defaults_to_none() -> None:
    from evra.__main__ import build_parser

    assert build_parser().parse_args(["run"]).data_dir is None


def test_capture_test_subcommand_is_registered() -> None:
    from evra.__main__ import build_parser

    args = build_parser().parse_args(["capture-test", "60", "--mic", "2"])
    assert args.command == "capture-test" and args.seconds == 60.0 and args.mic == "2"


def test_capture_test_rejects_non_positive_seconds() -> None:
    from evra.__main__ import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(["capture-test", "0"])
