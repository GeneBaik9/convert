"""Integration tests for patchport v2 — file similarity mapping phase."""

import subprocess
from pathlib import Path
from unittest.mock import patch
import pytest
from click.testing import CliRunner
from patchport.cli import main
from patchport.mapper import MAP_FILENAME, MAP_BACKUP_FILENAME, MappingCandidate


def _auto_confirm(candidates, target_files):
    """Mock show_mapping_ui: confirm suggested mapping as-is."""
    return candidates


@pytest.fixture
def diff_structure_repos(tmp_path: Path):
    """upstream: src/app.py — target: lib/app_v2.py (different path, similar content)."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    for cmd in [
        ["git", "init"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "Test"],
    ]:
        subprocess.run(cmd, cwd=upstream, check=True, capture_output=True)

    (upstream / "src").mkdir()
    (upstream / "src" / "app.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=upstream, check=True, capture_output=True)

    (upstream / "src" / "app.py").write_text("x = 2\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "bump x"], cwd=upstream, check=True, capture_output=True)

    target = tmp_path / "target"
    (target / "lib").mkdir(parents=True)
    (target / "lib" / "app_v2.py").write_text("x = 1\n")

    return upstream, target


@patch("patchport.cli.show_mapping_ui", side_effect=_auto_confirm)
def test_cli_v2_maps_and_patches_different_structure(_, diff_structure_repos):
    upstream, target = diff_structure_repos
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--upstream", str(upstream), "--target", str(target)],
        input="2\n1\n",
    )
    assert result.exit_code == 0, result.output
    assert (target / "lib" / "app_v2.py").read_text() == "x = 2\n"


@patch("patchport.cli.show_mapping_ui", side_effect=_auto_confirm)
def test_cli_v2_saves_map_file(_, diff_structure_repos):
    upstream, target = diff_structure_repos
    runner = CliRunner()
    runner.invoke(
        main,
        ["--upstream", str(upstream), "--target", str(target)],
        input="2\n1\n",
    )
    assert (target / MAP_FILENAME).exists()


@patch("patchport.cli.show_mapping_ui", side_effect=_auto_confirm)
def test_cli_v2_reuses_saved_map(_, diff_structure_repos):
    upstream, target = diff_structure_repos
    runner = CliRunner()
    # First run: build and save map
    runner.invoke(main, ["--upstream", str(upstream), "--target", str(target)], input="2\n1\n")
    # Reset target file
    (target / "lib" / "app_v2.py").write_text("x = 1\n")
    # Second run: should reuse saved map (show_mapping_ui NOT called again)
    result = runner.invoke(
        main, ["--upstream", str(upstream), "--target", str(target)], input="2\n1\n"
    )
    assert result.exit_code == 0, result.output
    assert "Loaded mapping" in result.output
    assert (target / "lib" / "app_v2.py").read_text() == "x = 2\n"


@patch("patchport.cli.show_mapping_ui", side_effect=_auto_confirm)
def test_cli_v2_remap_creates_backup(_, diff_structure_repos):
    upstream, target = diff_structure_repos
    runner = CliRunner()
    runner.invoke(main, ["--upstream", str(upstream), "--target", str(target)], input="2\n1\n")
    (target / "lib" / "app_v2.py").write_text("x = 1\n")
    runner.invoke(
        main,
        ["--upstream", str(upstream), "--target", str(target), "--remap"],
        input="2\n1\n",
    )
    assert (target / MAP_BACKUP_FILENAME).exists()


@patch("patchport.cli.show_mapping_ui", side_effect=_auto_confirm)
def test_cli_v2_dry_run_does_not_save_map(_, diff_structure_repos):
    upstream, target = diff_structure_repos
    runner = CliRunner()
    runner.invoke(
        main,
        ["--upstream", str(upstream), "--target", str(target), "--dry-run"],
        input="2\n1\n",
    )
    assert not (target / MAP_FILENAME).exists()
