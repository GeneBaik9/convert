import subprocess
from pathlib import Path
import pytest
from click.testing import CliRunner
from patchport.cli import main


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


def test_cli_applies_clean_patch(two_repos):
    upstream, target = two_repos
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--upstream", str(upstream), "--target", str(target)],
        input="2\n1\n",   # From #2 (older) → To #1 (newer)
    )
    assert result.exit_code == 0, result.output
    assert (target / "hello.py").read_text() == "msg = 'world'\n"


def test_cli_dry_run_does_not_modify(two_repos):
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
    # tmp_path exists but is not a git repo — exercises our NotAGitRepoError path
    target = tmp_path / "target"
    target.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--upstream", str(tmp_path), "--target", str(target)],
    )
    assert result.exit_code != 0


def test_cli_shows_commit_table(two_repos):
    upstream, target = two_repos
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--upstream", str(upstream), "--target", str(target)],
        input="2\n1\n",
    )
    assert "initial" in result.output
    assert "update msg" in result.output
