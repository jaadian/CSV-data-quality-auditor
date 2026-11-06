from pathlib import Path

from typer.testing import CliRunner

from csv_auditor.cli import app

runner = CliRunner()


def test_cli_clean_file_exit_zero(tmp_path: Path):
    csv_file = tmp_path / "valid.csv"
    csv_file.write_text("id,name\n1,Alpha\n2,Beta\n", encoding="utf-8")

    result = runner.invoke(app, ["analyze", str(csv_file), "--out-dir", str(tmp_path / "out")])
    assert result.exit_code == 0
    assert "Data Quality Audit Summary" in result.stdout


def test_cli_fail_on_threshold_exit_one(tmp_path: Path):
    csv_file = tmp_path / "has_duplicates.csv"
    csv_file.write_text("id,name\n1,Alpha\n1,Alpha\n", encoding="utf-8")

    result = runner.invoke(app, ["analyze", str(csv_file), "--fail-on", "high"])
    assert result.exit_code == 1


def test_cli_invalid_config_exit_two(tmp_path: Path):
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("id\n1\n", encoding="utf-8")
    cfg_file = tmp_path / "bad_config.yaml"
    cfg_file.write_text("unknown_root_key: true\n", encoding="utf-8")

    result = runner.invoke(app, ["analyze", str(csv_file), "--config", str(cfg_file)])
    assert result.exit_code == 2


def test_cli_missing_file_exit_three(tmp_path: Path):
    result = runner.invoke(app, ["analyze", str(tmp_path / "does_not_exist.csv")])
    assert result.exit_code == 3


def test_cli_empty_file_exit_three(tmp_path: Path):
    empty_file = tmp_path / "empty.csv"
    empty_file.write_text("", encoding="utf-8")
    result = runner.invoke(app, ["analyze", str(empty_file)])
    assert result.exit_code == 3
