from click.testing import CliRunner
from sentinel_diff.cli import main


def test_cli_presets():
    runner = CliRunner()
    result = runner.invoke(main, ["presets"])
    assert result.exit_code == 0
    assert "alibeykoy" in result.output
    assert "terkos" in result.output
    assert "omerli" in result.output


def test_cli_status():
    runner = CliRunner()
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert "Environment and modules ready" in result.output
