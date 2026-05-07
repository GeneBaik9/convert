import subprocess
from pathlib import Path
from unittest.mock import patch
import pytest
from click.testing import CliRunner
from patchport.cli import main
from patchport.mapper import MappingCandidate


def _auto_confirm(candidates, target_files):
    """Mock show_mapping_ui: confirm suggested mapping as-is."""
    return candidates


@pytest.fixture
def two_repos(tmp_path: Path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    for cmd in [
        ["git", "init"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "Test"],
    ]:
        subprocess.run(cmd, cwd=upstream, check=True, capture_output=True)

    (upstream / "hello.py").write_text("msg = 'hello'\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=upstream, check=True, capture_output=True)

    (upstream / "hello.py").write_text("msg = 'world'\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "update msg"], cwd=upstream, check=True, capture_output=True)

    target = tmp_path / "target"
    target.mkdir()
    (target / "hello.py").write_text("msg = 'hello'\n")
    return upstream, target


@patch("patchport.cli.show_mapping_ui", side_effect=_auto_confirm)
def test_cli_applies_clean_patch(_, two_repos):
    upstream, target = two_repos
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--upstream", str(upstream), "--target", str(target)],
        input="2\n1\n",
    )
    assert result.exit_code == 0, result.output
    assert (target / "hello.py").read_text() == "msg = 'world'\n"


@patch("patchport.cli.show_mapping_ui", side_effect=_auto_confirm)
def test_cli_dry_run_does_not_modify(_, two_repos):
    upstream, target = two_repos
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--upstream", str(upstream), "--target", str(target), "--dry-run"],
        input="2\n1\n",
    )
    assert result.exit_code == 0, result.output
    assert (target / "hello.py").read_text() == "msg = 'hello'\n"  # unchanged
    assert "Dry run" in result.output


def test_cli_invalid_upstream_exits_with_error(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--upstream", str(tmp_path), "--target", str(target)],
    )
    assert result.exit_code != 0


@patch("patchport.cli.show_mapping_ui", side_effect=_auto_confirm)
def test_cli_shows_commit_table(_, two_repos):
    upstream, target = two_repos
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--upstream", str(upstream), "--target", str(target)],
        input="2\n1\n",
    )
    assert "initial" in result.output
    assert "update msg" in result.output
