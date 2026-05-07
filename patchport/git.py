import subprocess
from pathlib import Path
from .exceptions import NotAGitRepoError, InvalidCommitRangeError


def list_commits(upstream: Path, limit: int = 20) -> list[dict]:
    """List commits from a Git repository.

    Args:
        upstream: Path to the Git repository
        limit: Maximum number of commits to return (default 20)

    Returns:
        List of dicts with keys: index, hash, short_hash, message, date

    Raises:
        NotAGitRepoError: If the path is not a valid Git repository
    """
    try:
        result = subprocess.run(
            [
                "git", "log",
                f"--max-count={limit}",
                "--format=%H\x1f%s\x1f%ad",
                "--date=short",
            ],
            cwd=upstream,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        raise NotAGitRepoError(upstream)

    if result.returncode != 0:
        raise NotAGitRepoError(upstream)
    lines = [ln for ln in result.stdout.strip().splitlines() if ln]
    commits = []
    for i, line in enumerate(lines, 1):
        hash_, message, date = line.split("\x1f", 2)
        commits.append(
            {
                "index": i,
                "hash": hash_,
                "short_hash": hash_[:7],
                "message": message,
                "date": date,
            }
        )
    return commits


def get_changed_files(upstream: Path, from_hash: str, to_hash: str) -> list[str]:
    """Get list of changed files between two commits.

    Args:
        upstream: Path to the Git repository
        from_hash: Starting commit hash (older)
        to_hash: Ending commit hash (newer)

    Returns:
        List of file paths that changed between the commits

    Raises:
        InvalidCommitRangeError: If the commit range is invalid
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{from_hash}..{to_hash}"],
        cwd=upstream,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise InvalidCommitRangeError(from_hash, to_hash)
    return [f for f in result.stdout.strip().splitlines() if f]


def show_file_at_commit(upstream: Path, commit_hash: str, file_path: str) -> str | None:
    """Show file content at a specific commit.

    Args:
        upstream: Path to the Git repository
        commit_hash: Commit hash to retrieve file from
        file_path: Path to the file within the repository

    Returns:
        File content as a string, or None if file doesn't exist at that commit
    """
    result = subprocess.run(
        ["git", "show", f"{commit_hash}:{file_path}"],
        cwd=upstream,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def show_file_bytes_at_commit(upstream: Path, commit_hash: str, file_path: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", f"{commit_hash}:{file_path}"],
        cwd=upstream,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout
