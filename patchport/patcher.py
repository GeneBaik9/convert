import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .exceptions import PatchApplicationError
from .git import get_changed_files, show_file_at_commit


@dataclass
class FileResult:
    path: str
    status: str  # "patched" | "conflict" | "skipped"
    conflict_count: int = 0


def apply_changes(
    upstream: Path, target: Path, from_hash: str, to_hash: str
) -> list[FileResult]:
    changed_files = get_changed_files(upstream, from_hash, to_hash)
    return [_merge_file(upstream, target, from_hash, to_hash, f) for f in changed_files]


def _merge_file(
    upstream: Path,
    target: Path,
    from_hash: str,
    to_hash: str,
    file_path: str,
) -> FileResult:
    old_content = show_file_at_commit(upstream, from_hash, file_path)
    new_content = show_file_at_commit(upstream, to_hash, file_path)
    local_file = target / file_path

    if new_content is None:
        return FileResult(path=file_path, status="skipped")

    if old_content is None or not local_file.exists():
        local_file.parent.mkdir(parents=True, exist_ok=True)
        local_file.write_text(new_content)
        return FileResult(path=file_path, status="patched")

    old_fd, old_path = tempfile.mkstemp(suffix=".base")
    new_fd, new_path = tempfile.mkstemp(suffix=".other")
    try:
        os.write(old_fd, old_content.encode())
        os.close(old_fd)
        os.write(new_fd, new_content.encode())
        os.close(new_fd)

        result = subprocess.run(
            [
                "git", "merge-file",
                "--diff3",
                "-L", "local",
                "-L", "upstream (base)",
                "-L", "upstream (new)",
                str(local_file),
                old_path,
                new_path,
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode < 0:
            raise PatchApplicationError(file_path, result.stderr)

        if result.returncode == 0:
            return FileResult(path=file_path, status="patched")

        content = local_file.read_text(errors="replace")
        count = content.count("<<<<<<< ")
        return FileResult(path=file_path, status="conflict", conflict_count=count)

    finally:
        for p in (old_path, new_path):
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass
