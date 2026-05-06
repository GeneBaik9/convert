import subprocess
from pathlib import Path
import pytest
from patchport.git import list_commits
from patchport.patcher import apply_changes, FileResult


@pytest.fixture
def repos(tmp_path: Path):
    """Upstream with 2 commits; target with local modifications."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    for cmd in [
        ["git", "init"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "Test"],
    ]:
        subprocess.run(cmd, cwd=upstream, check=True, capture_output=True)

    # Commit 1 (older): version=1, feature=False
    (upstream / "app.py").write_text("version = 1\nfeature = False\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=upstream, check=True, capture_output=True)

    # Commit 2 (newer): version=2, feature=True
    (upstream / "app.py").write_text("version = 2\nfeature = True\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "bump"], cwd=upstream, check=True, capture_output=True)

    target = tmp_path / "target"
    target.mkdir()
    # Local file matches old upstream on 'version', has own value for 'feature'
    (target / "app.py").write_text("version = 1\nfeature = 'my_override'\n")

    commits = list_commits(upstream)
    from_hash = commits[1]["hash"]  # older
    to_hash = commits[0]["hash"]    # newer
    return upstream, target, from_hash, to_hash


@pytest.fixture
def clean_repos(tmp_path: Path):
    """Upstream with 2 commits; target has no local divergence."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    for cmd in [
        ["git", "init"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "Test"],
    ]:
        subprocess.run(cmd, cwd=upstream, check=True, capture_output=True)

    (upstream / "app.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "v1"], cwd=upstream, check=True, capture_output=True)

    (upstream / "app.py").write_text("x = 2\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "v2"], cwd=upstream, check=True, capture_output=True)

    target = tmp_path / "target"
    target.mkdir()
    (target / "app.py").write_text("x = 1\n")  # identical to old upstream

    commits = list_commits(upstream)
    from_hash = commits[1]["hash"]
    to_hash = commits[0]["hash"]
    return upstream, target, from_hash, to_hash


def test_clean_merge_updates_file(clean_repos):
    upstream, target, from_hash, to_hash = clean_repos
    results = apply_changes(upstream, target, from_hash, to_hash)
    assert len(results) == 1
    assert results[0].path == "app.py"
    assert results[0].status == "patched"
    assert (target / "app.py").read_text() == "x = 2\n"


def test_conflict_inserts_markers(repos):
    upstream, target, from_hash, to_hash = repos
    results = apply_changes(upstream, target, from_hash, to_hash)
    assert len(results) == 1
    result = results[0]
    assert result.status == "conflict"
    assert result.conflict_count >= 1
    content = (target / "app.py").read_text()
    assert "<<<<<<< " in content
    assert "=======" in content
    assert ">>>>>>> " in content


def test_new_file_is_created(tmp_path: Path):
    """A file added in upstream is created in target."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    for cmd in [
        ["git", "init"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "Test"],
    ]:
        subprocess.run(cmd, cwd=upstream, check=True, capture_output=True)

    (upstream / "old.py").write_text("pass\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=upstream, check=True, capture_output=True)

    (upstream / "new.py").write_text("print('hello')\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add new.py"], cwd=upstream, check=True, capture_output=True)

    target = tmp_path / "target"
    target.mkdir()
    (target / "old.py").write_text("pass\n")

    commits = list_commits(upstream)
    results = apply_changes(upstream, target, commits[1]["hash"], commits[0]["hash"])

    new_file_result = next(r for r in results if r.path == "new.py")
    assert new_file_result.status == "patched"
    assert (target / "new.py").read_text() == "print('hello')\n"


def test_apply_changes_returns_list_of_file_results(clean_repos):
    upstream, target, from_hash, to_hash = clean_repos
    results = apply_changes(upstream, target, from_hash, to_hash)
    assert isinstance(results, list)
    assert all(isinstance(r, FileResult) for r in results)
