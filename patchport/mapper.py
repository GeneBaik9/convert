import json
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Optional

FILENAME_WEIGHT = 0.3
CONTENT_WEIGHT = 0.7
MATCH_THRESHOLD = 0.65

MAP_FILENAME = ".patchport-map.json"
MAP_BACKUP_FILENAME = ".patchport-map.json.bak"


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
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> list[MappingCandidate]:
    candidates = []
    n_up = len(upstream_files)
    n_tg = len(target_files)
    total_comparisons = n_up * n_tg
    PROGRESS_EVERY = 20

    for i, (up_path, up_bytes) in enumerate(upstream_files.items(), start=1):
        up_is_binary = is_binary(up_bytes)
        best_score = 0.0
        best_target: str | None = None

        for j, (tgt_path, tgt_bytes) in enumerate(target_files.items(), start=1):
            if progress_callback is not None:
                comp_idx = (i - 1) * n_tg + j
                if comp_idx % PROGRESS_EVERY == 0 or comp_idx == total_comparisons:
                    progress_callback(comp_idx, total_comparisons, f"{up_path} vs {tgt_path}")
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


def save_map(target_dir: Path, candidates: list[MappingCandidate]) -> None:
    mappings: dict = {}
    for c in candidates:
        if c.is_binary:
            mappings[c.upstream_path] = {
                "target": c.target_path,
                "binary": True,
                "action": c.action,
            }
        else:
            mappings[c.upstream_path] = c.target_path

    data = {
        "version": "2",
        "created": date.today().isoformat(),
        "mappings": mappings,
    }
    (target_dir / MAP_FILENAME).write_text(json.dumps(data, indent=2, ensure_ascii=False))


def load_map(target_dir: Path) -> list[MappingCandidate] | None:
    map_file = target_dir / MAP_FILENAME
    if not map_file.exists():
        return None

    from .exceptions import MappingFileError
    try:
        data = json.loads(map_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        raise MappingFileError(str(e))

    candidates = []
    for upstream_path, entry in data.get("mappings", {}).items():
        if isinstance(entry, dict):
            candidates.append(MappingCandidate(
                upstream_path=upstream_path,
                target_path=entry.get("target"),
                score=1.0,
                is_binary=True,
                action=entry.get("action", "overwrite"),
            ))
        else:
            target_path = entry  # str or None
            candidates.append(MappingCandidate(
                upstream_path=upstream_path,
                target_path=target_path,
                score=1.0,
                is_binary=False,
                action="merge" if target_path is not None else "skip",
            ))
    return candidates


def backup_map(target_dir: Path) -> None:
    map_file = target_dir / MAP_FILENAME
    if map_file.exists():
        bak = target_dir / MAP_BACKUP_FILENAME
        bak.write_bytes(map_file.read_bytes())
