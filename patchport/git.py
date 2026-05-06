import subprocess
from pathlib import Path
from .exceptions import NotAGitRepoError


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
    lines = [l for l in result.stdout.strip().splitlines() if l]
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
