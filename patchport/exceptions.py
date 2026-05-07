from pathlib import Path


class NotAGitRepoError(Exception):
    def __init__(self, path: Path) -> None:
        super().__init__(f"Not a Git repository: {path}")
        self.path = path


class InvalidCommitRangeError(Exception):
    def __init__(self, from_hash: str, to_hash: str) -> None:
        super().__init__(
            f"Invalid commit range: {from_hash[:7]}..{to_hash[:7]}. "
            "'From' must be an older commit than 'To'."
        )


class PatchApplicationError(Exception):
    def __init__(self, file_path: str, detail: str) -> None:
        super().__init__(f"Failed to apply patch to '{file_path}': {detail}")
        self.file_path = file_path


class MappingFileError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(
            f"Cannot read .patchport-map.json: {detail}. "
            "Run with --remap to rebuild the mapping."
        )
