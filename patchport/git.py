import subprocess
from functools import lru_cache
from pathlib import Path
from .exceptions import NotAGitRepoError, InvalidCommitRangeError


@lru_cache(maxsize=32)
def _detect_subpath(upstream: Path) -> tuple[Path, str]:
    """Return (git_root, subpath) for the given upstream path.

    subpath is "" if upstream IS the git root, otherwise it's the
    relative path from git_root to upstream (e.g. "embedded/firmware").
    Raises NotAGitRepoError if upstream is not inside a git repo.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=upstream, capture_output=True, text=True,
        )
    except (FileNotFoundError, NotADirectoryError):
        raise NotAGitRepoError(upstream)
    if result.returncode != 0:
        raise NotAGitRepoError(upstream)
    git_root = Path(result.stdout.strip()).resolve()
    try:
        rel = upstream.resolve().relative_to(git_root)
    except ValueError:
        return git_root, ""
    sub = str(rel).replace("\\", "/")
    return git_root, "" if sub == "." else sub


def list_commits(upstream: Path, limit: int = 20) -> list[dict]:
    """List commits from a Git repository.

    Args:
        upstream: Path to the Git repository (or a subdirectory within it)
        limit: Maximum number of commits to return (default 20)

    Returns:
        List of dicts with keys: index, hash, short_hash, message, date

    Raises:
        NotAGitRepoError: If the path is not a valid Git repository
    """
    git_root, subpath = _detect_subpath(upstream)
    args = ["git", "log", f"--max-count={limit}", "--format=%H\x1f%s\x1f%ad", "--date=short"]
    if subpath:
        args += ["--", subpath]
    result = subprocess.run(args, cwd=git_root, capture_output=True, text=True)
    if result.returncode != 0:
        raise NotAGitRepoError(upstream)
    lines = [ln for ln in result.stdout.strip().splitlines() if ln]
    commits = []
    for i, line in enumerate(lines, 1):
        hash_, message, date = line.split("\x1f", 2)
        commits.append({"index": i, "hash": hash_, "short_hash": hash_[:7], "message": message, "date": date})
    return commits


def get_changed_files(upstream: Path, from_hash: str, to_hash: str) -> list[str]:
    """Get list of changed files between two commits.

    Args:
        upstream: Path to the Git repository (or a subdirectory within it)
        from_hash: Starting commit hash (older)
        to_hash: Ending commit hash (newer)

    Returns:
        List of file paths that changed between the commits (relative to upstream)

    Raises:
        InvalidCommitRangeError: If the commit range is invalid
    """
    git_root, subpath = _detect_subpath(upstream)
    args = ["git", "diff", "--name-only", f"{from_hash}..{to_hash}"]
    if subpath:
        args += ["--", subpath]
    result = subprocess.run(args, cwd=git_root, capture_output=True, text=True)
    if result.returncode != 0:
        raise InvalidCommitRangeError(from_hash, to_hash)
    files = [f for f in result.stdout.strip().splitlines() if f]
    if subpath:
        prefix = subpath.rstrip("/") + "/"
        files = [f[len(prefix):] if f.startswith(prefix) else f for f in files]
    return files


def show_file_at_commit(upstream: Path, commit_hash: str, file_path: str) -> str | None:
    """Show file content at a specific commit.

    Args:
        upstream: Path to the Git repository (or a subdirectory within it)
        commit_hash: Commit hash to retrieve file from
        file_path: Path to the file relative to upstream

    Returns:
        File content as a string, or None if file doesn't exist at that commit
    """
    git_root, subpath = _detect_subpath(upstream)
    full = f"{subpath}/{file_path}" if subpath else file_path
    result = subprocess.run(
        ["git", "show", f"{commit_hash}:{full}"],
        cwd=git_root, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def show_file_bytes_at_commit(upstream: Path, commit_hash: str, file_path: str) -> bytes | None:
    git_root, subpath = _detect_subpath(upstream)
    full = f"{subpath}/{file_path}" if subpath else file_path
    result = subprocess.run(
        ["git", "show", f"{commit_hash}:{full}"],
        cwd=git_root, capture_output=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout
