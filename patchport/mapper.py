from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

FILENAME_WEIGHT = 0.3
CONTENT_WEIGHT = 0.7
MATCH_THRESHOLD = 0.65


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


def build_candidates(
    upstream_files: dict[str, bytes],
    target_files: dict[str, bytes],
) -> list[MappingCandidate]:
    candidates = []

    for up_path, up_bytes in upstream_files.items():
        up_is_binary = is_binary(up_bytes)
        best_score = 0.0
        best_target: str | None = None

        for tgt_path, tgt_bytes in target_files.items():
            score = compute_score(up_path, up_bytes, tgt_path, tgt_bytes)
            if score > best_score:
                best_score = score
                best_target = tgt_path

        # Apply threshold check, but be lenient with binary files if filenames match exactly
        if best_score < MATCH_THRESHOLD:
            if not (up_is_binary and best_target and Path(up_path).name == Path(best_target).name):
                best_target = None

        if best_target is None:
            action = "skip"
        elif up_is_binary:
            action = "overwrite"
        else:
            action = "merge"

        candidates.append(
            MappingCandidate(
                upstream_path=up_path,
                target_path=best_target,
                score=best_score,
                is_binary=up_is_binary,
                action=action,
            )
        )

    return sorted(candidates, key=lambda c: c.score, reverse=True)
