from click.testing import CliRunner

from sentinel_diff import __version__
from sentinel_diff.cli import main


def test_version():
    assert __version__ == "0.1.0"


def test_cli_status():
    runner = CliRunner()
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0
    assert "sentinel-diff v0.1.0" in result.output
