from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

FILENAME_WEIGHT = 0.3
CONTENT_WEIGHT = 0.7
MATCH_THRESHOLD = 0.5


@dataclass
class MappingCandidate:
    upstream_path: str
    target_path: str | None     # None = unmapped/skip
    score: float                # 0.0 to 1.0
    is_binary: bool
    action: str                 # "merge" | "overwrite" | "skip"


def is_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def compute_score(
    upstream_path: str,
    upstream_bytes: bytes,
    target_path: str,
    target_bytes: bytes,
) -> float:
    name_score = SequenceMatcher(
        None,
        Path(upstream_path).name,
        Path(target_path).name,
    ).ratio()

    if is_binary(upstream_bytes) or is_binary(target_bytes):
        return FILENAME_WEIGHT * name_score

    upstream_text = upstream_bytes.decode("utf-8", errors="replace")
    target_text = target_bytes.decode("utf-8", errors="replace")
    content_score = SequenceMatcher(None, upstream_text, target_text).ratio()

    return FILENAME_WEIGHT * name_score + CONTENT_WEIGHT * content_score
