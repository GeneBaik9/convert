import json
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Optional

FILENAME_WEIGHT = 0.3
CONTENT_WEIGHT = 0.7
MATCH_THRESHOLD = 0.65

# Cap content size for SequenceMatcher comparison.
# SequenceMatcher.ratio() is ~O(N²) on large content; this prevents pathological
# slowdowns on big files (data files, generated code, etc.).
MAX_COMPARE_BYTES = 100_000

MAP_FILENAME = ".patchport-map.json"
MAP_BACKUP_FILENAME = ".patchport-map.json.bak"


def _ext(path: str) -> str:
    """Return lowercase extension (e.g. '.py'), or '' if none."""
    return Path(path).suffix.lower()


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

    # Cap content size — SequenceMatcher on huge files takes minutes
    upstream_text = upstream_bytes[:MAX_COMPARE_BYTES].decode("utf-8", errors="replace")
    target_text = target_bytes[:MAX_COMPARE_BYTES].decode("utf-8", errors="replace")
    content_score = SequenceMatcher(None, upstream_text, target_text).ratio()

    return FILENAME_WEIGHT * name_score + CONTENT_WEIGHT * content_score


def build_candidates(
    upstream_files: dict[str, bytes],
    target_files: dict[str, bytes],
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> list[MappingCandidate]:
    """Build similarity-based mapping candidates.

    Optimizations:
    - Targets are grouped by extension; only same-extension files are compared
      (a .h file is never compared to a .md file)
    - Upstream content is decoded once per upstream file, not per comparison
    - quick_ratio() is used as an upper-bound filter before the expensive ratio()
    """
    # Group target files by extension for fast lookup
    target_by_ext: dict[str, list[tuple[str, bytes]]] = {}
    for tgt_path, tgt_bytes in target_files.items():
        target_by_ext.setdefault(_ext(tgt_path), []).append((tgt_path, tgt_bytes))

    # Total comparisons = sum of per-upstream candidate counts (only same-extension)
    total_comparisons = sum(
        len(target_by_ext.get(_ext(up_path), [])) for up_path in upstream_files
    )

    candidates: list[MappingCandidate] = []
    comp_idx = 0

    for up_path, up_bytes in upstream_files.items():
        up_is_binary = is_binary(up_bytes)
        up_ext = _ext(up_path)
        candidate_targets = target_by_ext.get(up_ext, [])
        up_basename = Path(up_path).name

        # Pre-decode upstream content once (not per comparison)
        up_text_capped = (
            "" if up_is_binary
            else up_bytes[:MAX_COMPARE_BYTES].decode("utf-8", errors="replace")
        )

        best_score = 0.0
        best_target: str | None = None

        for tgt_path, tgt_bytes in candidate_targets:
            comp_idx += 1
            if progress_callback is not None:
                progress_callback(comp_idx, total_comparisons, f"{up_path} vs {tgt_path}")

            tg_is_binary = is_binary(tgt_bytes)
            name_score = SequenceMatcher(
                None, up_basename, Path(tgt_path).name
            ).ratio()

            if up_is_binary or tg_is_binary:
                score = FILENAME_WEIGHT * name_score
            else:
                tg_text_capped = tgt_bytes[:MAX_COMPARE_BYTES].decode(
                    "utf-8", errors="replace"
                )
                sm = SequenceMatcher(None, up_text_capped, tg_text_capped)
                # quick_ratio is a fast upper bound on ratio
                upper = FILENAME_WEIGHT * name_score + CONTENT_WEIGHT * sm.quick_ratio()
                if upper <= best_score:
                    # Cannot beat current best — skip the expensive ratio() call
                    continue
                content_score = sm.ratio()
                score = FILENAME_WEIGHT * name_score + CONTENT_WEIGHT * content_score

            if score > best_score:
                best_score = score
                best_target = tgt_path

        # Threshold check (binary fallback: identical filename ok even below threshold)
        if best_score < MATCH_THRESHOLD:
            if not (up_is_binary and best_target and up_basename == Path(best_target).name):
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
