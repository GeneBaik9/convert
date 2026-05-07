import subprocess
from pathlib import Path
import pytest
from patchport.git import list_commits
from patchport.mapper import MappingCandidate
from patchport.patcher import apply_changes, FileResult


def _identity_candidate(file_path: str) -> MappingCandidate:
    return MappingCandidate(
        upstream_path=file_path,
        target_path=file_path,
        score=1.0,
        is_binary=False,
        action="merge",
    )


@pytest.fixture
def repos(tmp_path: Path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    for cmd in [
        ["git", "init"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "Test"],
    ]:
        subprocess.run(cmd, cwd=upstream, check=True, capture_output=True)

    (upstream / "app.py").write_text("version = 1\nfeature = False\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=upstream, check=True, capture_output=True)

    (upstream / "app.py").write_text("version = 2\nfeature = True\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "bump"], cwd=upstream, check=True, capture_output=True)

    target = tmp_path / "target"
    target.mkdir()
    (target / "app.py").write_text("version = 1\nfeature = 'my_override'\n")

    commits = list_commits(upstream)
    from_hash = commits[1]["hash"]
    to_hash = commits[0]["hash"]
    return upstream, target, from_hash, to_hash


@pytest.fixture
def clean_repos(tmp_path: Path):
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
    (target / "app.py").write_text("x = 1\n")

    commits = list_commits(upstream)
    from_hash = commits[1]["hash"]
    to_hash = commits[0]["hash"]
    return upstream, target, from_hash, to_hash


def test_clean_merge_updates_file(clean_repos):
    upstream, target, from_hash, to_hash = clean_repos
    candidates = [_identity_candidate("app.py")]
    results = apply_changes(upstream, target, from_hash, to_hash, candidates)
    assert len(results) == 1
    assert results[0].path == "app.py"
    assert results[0].status == "patched"
    assert (target / "app.py").read_text() == "x = 2\n"


def test_conflict_inserts_markers(repos):
    upstream, target, from_hash, to_hash = repos
    candidates = [_identity_candidate("app.py")]
    results = apply_changes(upstream, target, from_hash, to_hash, candidates)
    assert len(results) == 1
    assert results[0].status == "conflict"
    assert results[0].conflict_count >= 1
    content = (target / "app.py").read_text()
    assert "<<<<<<< " in content
    assert "=======" in content
    assert ">>>>>>> " in content


def test_new_file_is_created(tmp_path: Path):
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
    candidates = [_identity_candidate("new.py")]
    results = apply_changes(upstream, target, commits[1]["hash"], commits[0]["hash"], candidates)

    new_file_result = next(r for r in results if r.path == "new.py")
    assert new_file_result.status == "patched"
    assert (target / "new.py").read_text() == "print('hello')\n"


def test_apply_changes_returns_list_of_file_results(clean_repos):
    upstream, target, from_hash, to_hash = clean_repos
    candidates = [_identity_candidate("app.py")]
    results = apply_changes(upstream, target, from_hash, to_hash, candidates)
    assert isinstance(results, list)
    assert all(isinstance(r, FileResult) for r in results)


def test_skip_action_returns_skipped(clean_repos):
    upstream, target, from_hash, to_hash = clean_repos
    candidates = [
        MappingCandidate("app.py", None, 0.1, False, "skip")
    ]
    results = apply_changes(upstream, target, from_hash, to_hash, candidates)
    assert results[0].status == "skipped"


def test_path_mapping_applies_to_different_target_file(clean_repos):
    upstream, target, from_hash, to_hash = clean_repos
    # upstream: app.py → target: lib/app_v2.py (renamed)
    (target / "lib").mkdir()
    (target / "lib" / "app_v2.py").write_text("x = 1\n")  # same as old upstream
    candidates = [
        MappingCandidate("app.py", "lib/app_v2.py", 0.9, False, "merge")
    ]
    results = apply_changes(upstream, target, from_hash, to_hash, candidates)
    assert results[0].status == "patched"
    assert (target / "lib" / "app_v2.py").read_text() == "x = 2\n"


def test_binary_overwrite_action(tmp_path: Path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    for cmd in [
        ["git", "init"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "Test"],
    ]:
        subprocess.run(cmd, cwd=upstream, check=True, capture_output=True)

    (upstream / "logo.png").write_bytes(b"\x89PNG\x00old")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=upstream, check=True, capture_output=True)

    (upstream / "logo.png").write_bytes(b"\x89PNG\x00new")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "update logo"], cwd=upstream, check=True, capture_output=True)

    target = tmp_path / "target"
    target.mkdir()
    (target / "logo.png").write_bytes(b"\x89PNG\x00local")

    commits = list_commits(upstream)
    candidates = [
        MappingCandidate("logo.png", "logo.png", 0.8, True, "overwrite")
    ]
    results = apply_changes(upstream, target, commits[1]["hash"], commits[0]["hash"], candidates)
    assert results[0].status == "patched"
    assert (target / "logo.png").read_bytes() == b"\x89PNG\x00new"
