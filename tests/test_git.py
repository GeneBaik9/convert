import subprocess
from pathlib import Path
import pytest
from patchport.git import list_commits
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
