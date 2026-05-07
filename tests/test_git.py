import subprocess
from pathlib import Path
import pytest
from patchport.git import list_commits, get_changed_files, show_file_at_commit, show_file_bytes_at_commit
from patchport.exceptions import NotAGitRepoError


@pytest.fixture
def upstream_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "upstream"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    (repo / "main.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo, check=True, capture_output=True)
    (repo / "main.py").write_text("x = 2\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "bump x to 2"], cwd=repo, check=True, capture_output=True)
    return repo


def test_list_commits_returns_newest_first(upstream_repo: Path) -> None:
    commits = list_commits(upstream_repo)
    assert commits[0]["message"] == "bump x to 2"
    assert commits[1]["message"] == "initial commit"


def test_list_commits_fields(upstream_repo: Path) -> None:
    commits = list_commits(upstream_repo)
    c = commits[0]
    assert "index" in c
    assert "hash" in c
    assert "short_hash" in c
    assert "message" in c
    assert "date" in c
    assert c["index"] == 1
    assert len(c["hash"]) == 40
    assert len(c["short_hash"]) == 7


def test_list_commits_limit(upstream_repo: Path) -> None:
    commits = list_commits(upstream_repo, limit=1)
    assert len(commits) == 1
    assert commits[0]["message"] == "bump x to 2"


def test_list_commits_raises_for_non_repo(tmp_path: Path) -> None:
    with pytest.raises(NotAGitRepoError):
        list_commits(tmp_path / "not_a_repo")


def test_get_changed_files(upstream_repo: Path) -> None:
    commits = list_commits(upstream_repo)
    from_hash = commits[1]["hash"]  # older
    to_hash = commits[0]["hash"]    # newer
    files = get_changed_files(upstream_repo, from_hash, to_hash)
    assert files == ["main.py"]


def test_get_changed_files_empty_range(upstream_repo: Path) -> None:
    commits = list_commits(upstream_repo)
    same = commits[0]["hash"]
    files = get_changed_files(upstream_repo, same, same)
    assert files == []


def test_show_file_at_older_commit(upstream_repo: Path) -> None:
    commits = list_commits(upstream_repo)
    older_hash = commits[1]["hash"]
    content = show_file_at_commit(upstream_repo, older_hash, "main.py")
    assert content == "x = 1\n"


def test_show_file_at_newer_commit(upstream_repo: Path) -> None:
    commits = list_commits(upstream_repo)
    newer_hash = commits[0]["hash"]
    content = show_file_at_commit(upstream_repo, newer_hash, "main.py")
    assert content == "x = 2\n"


def test_show_file_returns_none_for_missing_file(upstream_repo: Path) -> None:
    commits = list_commits(upstream_repo)
    result = show_file_at_commit(upstream_repo, commits[0]["hash"], "nonexistent.py")
    assert result is None


def test_show_file_bytes_at_commit(upstream_repo: Path) -> None:
    commits = list_commits(upstream_repo)
    result = show_file_bytes_at_commit(upstream_repo, commits[1]["hash"], "main.py")
    assert result == b"x = 1\n"


def test_show_file_bytes_returns_none_for_missing(upstream_repo: Path) -> None:
    commits = list_commits(upstream_repo)
    result = show_file_bytes_at_commit(upstream_repo, commits[0]["hash"], "nonexistent.py")
    assert result is None


@pytest.fixture
def subdir_repo(tmp_path: Path):
    """Repo with two top-level dirs: embedded/ and other/. Upstream points at embedded/."""
    repo = tmp_path / "monorepo"
    repo.mkdir()
    for cmd in [
        ["git", "init"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "Test"],
    ]:
        subprocess.run(cmd, cwd=repo, check=True, capture_output=True)

    (repo / "embedded").mkdir()
    (repo / "embedded" / "main.c").write_text("int x = 1;\n")
    (repo / "other").mkdir()
    (repo / "other" / "doc.md").write_text("# docs\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)

    (repo / "embedded" / "main.c").write_text("int x = 2;\n")
    (repo / "other" / "doc.md").write_text("# docs updated\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "bump"], cwd=repo, check=True, capture_output=True)

    return repo / "embedded"


def test_list_commits_filters_to_subdir(subdir_repo: Path) -> None:
    # commits should reflect only embedded/ touches (still 2 since both commits touched it)
    commits = list_commits(subdir_repo)
    assert len(commits) == 2


def test_get_changed_files_strips_subdir_prefix(subdir_repo: Path) -> None:
    commits = list_commits(subdir_repo)
    files = get_changed_files(subdir_repo, commits[1]["hash"], commits[0]["hash"])
    # Should return main.c (not embedded/main.c) and exclude other/doc.md
    assert "main.c" in files
    assert not any(f.startswith("embedded/") for f in files)
    assert not any("other/" in f or "doc.md" in f for f in files)


def test_show_file_at_commit_resolves_subdir(subdir_repo: Path) -> None:
    commits = list_commits(subdir_repo)
    content = show_file_at_commit(subdir_repo, commits[0]["hash"], "main.c")
    assert content == "int x = 2;\n"


def test_show_file_bytes_at_commit_resolves_subdir(subdir_repo: Path) -> None:
    commits = list_commits(subdir_repo)
    content = show_file_bytes_at_commit(subdir_repo, commits[1]["hash"], "main.c")
    assert content == b"int x = 1;\n"


def test_root_upstream_still_works(subdir_repo: Path) -> None:
    # Pointing at the repo root should include other/doc.md too
    repo_root = subdir_repo.parent
    commits = list_commits(repo_root)
    files = get_changed_files(repo_root, commits[1]["hash"], commits[0]["hash"])
    assert "embedded/main.c" in files
    assert "other/doc.md" in files
