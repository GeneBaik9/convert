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
